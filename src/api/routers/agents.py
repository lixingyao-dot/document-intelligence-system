"""Agent 编排 API 路由"""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import unquote

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from config import load_config
from core.storage import build_blob_name, download_file_to_local, upload_file_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import add_session_file, get_session_by_id, get_session_files

router = APIRouter(prefix="/api/agents", tags=["Agent编排"])

# ============ Agent 能力定义 ============

MODES = [
    {
        "id": "default_conversation",
        "name": "默认对话",
        "description": "自由对话，通用问答",
        "requires_data": False,
        "requires_template": False,
    },
    {
        "id": "document_understanding",
        "name": "文档理解",
        "description": "上传文档后可交互式提问",
        "requires_data": True,
        "requires_template": False,
    },
    {
        "id": "document_editing",
        "name": "文档编辑",
        "description": "自然语言编辑Word/Excel/文本",
        "requires_data": True,
        "requires_template": False,
    },
    {
        "id": "entity_extraction",
        "name": "实体提取",
        "description": "从文档提取结构化数据",
        "requires_data": True,
        "requires_template": None,  # 可选
    },
    {
        "id": "table_filling",
        "name": "表格填表",
        "description": "条件筛选并填入模板",
        "requires_data": True,
        "requires_template": True,
    },
]


class TaskSpec(BaseModel):
    mode: str = Field(..., description="模式: default_conversation, document_understanding, etc.")
    content: str = Field(..., description="任务内容")
    session_id: str = Field(..., description="会话ID")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="关联文件列表")


class AgentCapabilitiesResponse(BaseModel):
    modes: List[Dict[str, Any]]


class MixedFillRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="合并后的结构化实体")
    template_file: str = Field(..., description="模板文件绝对路径")
    output_json: str = Field(default="", description="输出JSON路径（可选）")
    output_template: str = Field(default="", description="输出模板路径（可选）")
    template_sheet_name: str = Field(default="", description="模板sheet（可选）")
    template_header_row: int | None = Field(default=None, description="模板表头行（可选）")
    template_start_row: int | None = Field(default=None, description="模板起始行（可选）")
    template_table_index: int | None = Field(default=None, description="docx模板表索引（可选）")


@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
async def get_capabilities():
    """获取所有 Agent 能力"""
    return AgentCapabilitiesResponse(modes=MODES)


@router.post("/execute")
async def execute_task(task: TaskSpec):
    """
    直接执行 Agent 任务
    此端点用于前端直接调用 Agent，不走 WebSocket
    """
    from service.agent_service import AgentService
    
    agent_service = AgentService()
    result = await agent_service.execute_task(
        session_id=task.session_id,
        mode=task.mode,
        content=task.content,
        files=task.files,
    )
    return result


@router.post("/mixed-fill")
async def mixed_fill(request: MixedFillRequest, authorization: str | None = Header(default=None)):
    """统一填表：将mixed模式合并实体写入一个模板（xlsx/docx）。"""
    import shutil
    from pathlib import Path

    from core.agents.agent_d import run_agent_d_fill_from_entities

    cfg = load_config()
    current_user = None
    if authorization:
        try:
            current_user = resolve_user_from_authorization(authorization, cfg, required=True)
        except PermissionError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail=str(exc))
    elif cfg.auth.require_auth:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="需要登录后访问")

    print(
        f"[API] POST /api/agents/mixed-fill session_id={request.session_id} "
        f"template_file={request.template_file} entities={len(request.entities)}"
    )

    session = get_session_by_id(request.session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="会话不存在")

    uploads_dir = Path("workspace/uploads") / request.session_id
    uploads_dir.mkdir(parents=True, exist_ok=True)

    template_ref = unquote(str(request.template_file or "").strip())
    template_source = Path(template_ref)
    if not template_source.exists():
        # 兼容前端仅传 storage_key/file_name 的场景：从当前会话文件中反查本地 file_path
        session_files = get_session_files(request.session_id, config=cfg, user_id=current_user.id if current_user else None)
        matched = None
        ref_name = Path(template_ref).name if template_ref else ""
        for f in session_files:
            sk = str(f.storage_key or "")
            fn = str(f.file_name or "")
            if (
                (sk and (sk == template_ref or sk.endswith(template_ref) or template_ref.endswith(sk)))
                or (fn and (fn == template_ref or (ref_name and fn == ref_name)))
            ):
                matched = f
                break
        if matched and matched.file_path:
            candidate = Path(str(matched.file_path))
            if candidate.exists():
                template_source = candidate
        if not template_source.exists() and matched and matched.storage_key:
            # 若本地 file_path 不存在，尝试从存储下载到缓存目录
            try:
                cache_path = Path(cfg.temp_dir) / "file_cache" / request.session_id / "template" / (matched.file_name or ref_name or "template.xlsx")
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                template_source = Path(download_file_to_local(str(matched.storage_key), cache_path, config=cfg))
            except Exception:
                pass
        if not template_source.exists() and ref_name:
            # 按 basename 再兜底一次
            for f in session_files:
                if str(f.file_name or "") == ref_name and f.file_path:
                    candidate = Path(str(f.file_path))
                    if candidate.exists():
                        template_source = candidate
                        break

    if not template_source.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"模板文件不存在: {template_ref}")

    if "workspace/temp_uploads" in str(template_source):
        template_dest = uploads_dir / template_source.name
        shutil.copy2(template_source, template_dest)
        effective_template = str(template_dest)
    else:
        effective_template = str(template_source.resolve())

    output_template_path = str(uploads_dir / f"{Path(effective_template).stem}_filled{Path(effective_template).suffix}")
    output_json_path = str(uploads_dir / f"{Path(effective_template).stem}_merged_rows.json")

    result = run_agent_d_fill_from_entities(
        entities=request.entities,
        template=effective_template,
        output_json=output_json_path,
        output_template=output_template_path,
        template_sheet_name=request.template_sheet_name,
        template_header_row=request.template_header_row,
        template_start_row=request.template_start_row,
        template_table_index=request.template_table_index,
    )

    output_template_file = result.get("data", {}).get("template_output") if isinstance(result, dict) else None
    output_json_file = result.get("data", {}).get("output_json") if isinstance(result, dict) else None
    print(f"[API] mixed-fill 结果 template_output={output_template_file} output_json={output_json_file}")

    file_ids = []
    for candidate in [output_template_file, output_json_file]:
        if not candidate:
            continue
        path_obj = Path(str(candidate))
        if not path_obj.exists():
            continue
        try:
            if path_obj.parent != uploads_dir.resolve():
                dest = uploads_dir / path_obj.name
                shutil.copy2(path_obj, dest)
                path_obj = dest
            storage_key = None
            try:
                storage_key = upload_file_to_storage(
                    path_obj,
                    config=cfg,
                    blob_name=build_blob_name(request.session_id, path_obj.name, prefix=cfg.storage.object_key_prefix),
                )
            except Exception:
                storage_key = None
            session_file = add_session_file(
                session_id=request.session_id,
                file_name=path_obj.name,
                file_type="generated",
                file_path=str(path_obj),
                file_size=path_obj.stat().st_size,
                config=cfg,
                user_id=current_user.id if current_user else None,
                source="generated",
                role="output",
                storage_key=storage_key,
            )
            file_ids.append({"file_id": session_file.id, "file_name": path_obj.name, "file_path": str(path_obj)})
        except Exception:
            continue

    if isinstance(result, dict) and "data" in result:
        result["data"]["file_ids"] = file_ids

    return result

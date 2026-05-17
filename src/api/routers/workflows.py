"""
Workflow API 路由
支持前端工作流节点的执行调度，逐文件处理。

端点：
  POST /api/workflows/execute        启动执行，返回 execution_id
  GET  /api/workflows/executions/{id}  查询执行状态
  GET  /api/workflows                获取用户工作流列表
  POST /api/workflows                保存工作流（新建或更新）
  DELETE /api/workflows/{id}         删除工作流
  GET  /api/workflows/{id}           获取单个工作流完整配置
  GET  /api/workflows/models         获取可用 LLM 模型
  GET  /api/workflows/languages      获取支持的目标语言
  GET  /api/workflows/output-formats  获取支持的输出格式
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from config import SystemConfig, get_config
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType
from core.storage import build_blob_name, upload_file_to_storage, oss_storage_enabled
from db.auth_repository import resolve_user_from_authorization
from db.connection import is_database_configured
from db.workflow_repository import db_load_execution_states, db_save_execution_states, is_db_enabled
from db.session_repository import add_session_file, get_session_by_id
from utils.desktop_runtime import get_desktop_local_library, is_desktop_app
from utils.logger import get_logger
from starter_workflows import seed_starter_workflows_if_empty
from workflow_storage import delete_workflow, get_workflow, list_workflows, save_workflow

router = APIRouter(prefix="/api/workflows", tags=["工作流编排"])
logger = get_logger(__name__)


def _library_storage_ready(config: SystemConfig) -> bool:
    if get_desktop_local_library() is not None:
        return True
    return config.database.enabled and is_database_configured(config)


# ==================== 执行状态存储（进程内内存） ====================
# key: execution_id, value: state dict
_EXECUTION_STATES: Dict[str, dict] = {}
_EXECUTION_STATES_LOCK = threading.Lock()
_EXECUTION_STATES_HYDRATED = False


def _hydrate_execution_states() -> None:
    """首次访问时再加载持久化状态，避免多进程 import 时并发 DDL 死锁。"""
    global _EXECUTION_STATES_HYDRATED
    if _EXECUTION_STATES_HYDRATED:
        return
    with _EXECUTION_STATES_LOCK:
        if _EXECUTION_STATES_HYDRATED:
            return
        _EXECUTION_STATES.update(_load_execution_states())
        _EXECUTION_STATES_HYDRATED = True


def _execution_states_file(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    state_dir = Path(cfg.work_dir) / "workflows"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "execution_states.json"


def _load_execution_states(config: Optional[SystemConfig] = None) -> Dict[str, dict]:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        loaded = db_load_execution_states(cfg)
        if loaded:
            return loaded

    path = _execution_states_file(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning(f"加载工作流执行状态失败: {exc}")
    return {}


def _persist_execution_states(config: Optional[SystemConfig] = None) -> None:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        if db_save_execution_states(_EXECUTION_STATES, cfg):
            return

    path = _execution_states_file(config)
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(_EXECUTION_STATES, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception as exc:
        logger.warning(f"持久化工作流执行状态失败: {exc}")
        if tmp_path.exists():
            tmp_path.unlink()


# ==================== Request / Response 模型 ====================


class WorkflowNode(BaseModel):
    id: str
    type: str
    title: str
    schemaKey: Optional[str] = None
    configValues: Dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    workflowId: str = Field(..., description="工作流 ID")
    nodes: List[WorkflowNode] = Field(default_factory=list, description="工作流节点配置")
    docs: List[str] = Field(default_factory=list, description="文档库文档 ID 列表")
    localFiles: List[Dict[str, Any]] = Field(
        default_factory=list, description="本地上传文件 [{name, size, content(base64)}]"
    )
    sessionId: Optional[str] = Field(None, description="会话 ID（可选）")


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    progress: int = 0
    current_file_index: int = 0
    total_files: int = 0
    current_file_name: str = ""
    current_node_id: str = ""
    current_node_name: str = ""
    current_node_index: int = 0
    total_nodes: int = 0
    node_progress: List[Dict[str, Any]] = Field(default_factory=list)
    logs: List[Dict[str, str]] = Field(default_factory=list)
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None


# ==================== 辅助函数 ====================


def _normalize_output_mode(raw: Any) -> str:
    """library：写入文档库；external/download：仅本地目录输出（可下载）。"""
    mode = str(raw or "library").strip().lower()
    if mode in {"download", "external", "file", "folder", "local", "path"}:
        return "external"
    return "library"


def _get_output_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输出节点配置。优先「输出文件/文档库」节点，否则用第一个输出节点。"""
    first_output: Dict[str, Any] = {}
    for node in nodes:
        if node.type != "output":
            continue
        cv = dict(node.configValues or {})
        cv["_schemaKey"] = node.schemaKey
        if node.schemaKey == "schema-save-excel":
            cv.setdefault("outputFormat", "xlsx")
        elif node.schemaKey == "schema-save-text":
            cv.setdefault("outputFormat", "txt")
        if not first_output:
            first_output = cv
        # 画布上可能存在多个输出型节点时的歧义处理
        if node.schemaKey == "schema-library-output":
            return cv
        if node.schemaKey in {"schema-save-excel", "schema-save-text"}:
            return cv
    return first_output


def _get_input_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输入节点配置。"""
    for node in nodes:
        if node.type == "input":
            return node.configValues or {}
    return {}


def _get_translation_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取翻译/AI节点配置。"""
    for node in nodes:
        if node.type in ("translate", "ai"):
            return node.configValues or {}
    return {"targetLanguage": "中文"}


def _get_processing_nodes(nodes: List[WorkflowNode]) -> List[WorkflowNode]:
    """从节点列表中提取所有处理节点（排除输入/输出节点）。"""
    processing = []
    for node in nodes:
        if node.type not in ("input", "output"):
            processing.append(node)
    return processing


def _build_node_progress(nodes: List[WorkflowNode]) -> List[Dict[str, Any]]:
    progress_items: List[Dict[str, Any]] = []
    for idx, node in enumerate(nodes, start=1):
        progress_items.append(
            {
                "id": node.id,
                "title": node.title,
                "type": node.type,
                "schemaKey": node.schemaKey,
                "index": idx,
                "status": "pending",
                "progress": 0,
                "message": "",
            }
        )
    return progress_items


def _validate_execute_request(request: ExecuteRequest) -> List[str]:
    errors: List[str] = []
    errors.extend(_validate_pipeline_shape(list(request.nodes)))
    for idx, node in enumerate(request.nodes, start=1):
        schema_key = str(node.schemaKey or "").strip()
        cv = node.configValues or {}
        title = node.title or schema_key or f"第{idx}个节点"

        if schema_key == "schema-data-process":
            process_kind = str(cv.get("processKind") or "").strip()
            if process_kind not in {"sort", "filter", "aggregate", "dedupe", "fill_null", "computed_column", "merge_columns", "split_column"}:
                errors.append(f"{title}：processKind配置无效")
            required_by_kind = {
                "sort": ["sortColumn"],
                "filter": ["filterExpr"],
                "aggregate": ["aggregateColumn", "aggregateOp"],
                "fill_null": ["fillColumns"],
                "computed_column": ["computedColumnName", "computedFormula"],
                "merge_columns": ["mergeSourceColumns", "mergeTargetColumn"],
                "split_column": ["splitSourceColumn", "splitIntoColumns"],
            }
            missing = [key for key in required_by_kind.get(process_kind, []) if not str(cv.get(key) or "").strip()]
            if missing:
                errors.append(f"{title}：缺少配置 {', '.join(missing)}")
        elif schema_key == "schema-data-clean":
            rules = cv.get("cleanRules")
            if not rules:
                errors.append(f"{title}：cleanRules不能为空")
        elif schema_key == "schema-table-extract":
            strategy = str(cv.get("tableStrategy") or "first").strip()
            if strategy not in {"first", "all", "by_index"}:
                errors.append(f"{title}：tableStrategy配置无效")
            if strategy == "by_index":
                try:
                    if int(cv.get("tableIndex")) <= 0:
                        raise ValueError()
                except Exception:
                    errors.append(f"{title}：tableIndex必须是从1开始的正整数")
        elif schema_key == "schema-save-excel":
            sheet_name = str(cv.get("sheetName") or "Sheet1")
            if len(sheet_name) > 31:
                errors.append(f"{title}：sheetName不能超过31个字符")
            if any(ch in sheet_name for ch in '[]:*?/\\'):
                errors.append(f"{title}：sheetName不能包含 []:*?/\\")
        elif schema_key == "schema-save-text":
            encoding = str(cv.get("outputEncoding") or "utf-8").lower()
            if encoding not in {"utf-8", "gbk"}:
                errors.append(f"{title}：outputEncoding仅支持utf-8或gbk")
            line_ending = str(cv.get("lineEnding") or "lf").lower()
            if line_ending not in {"lf", "crlf"}:
                errors.append(f"{title}：lineEnding仅支持lf或crlf")

    return errors


def _validate_pipeline_shape(nodes: List[WorkflowNode]) -> List[str]:
    """画布约定：仅此 1 个输入在首位、1 个输出在末位，中间仅用处理节点。"""
    errs: List[str] = []
    if not nodes:
        return ["工作流节点不能为空"]
    ins = [(i, n) for i, n in enumerate(nodes) if str(n.type or "").lower() == "input"]
    outs = [(i, n) for i, n in enumerate(nodes) if str(n.type or "").lower() == "output"]
    if len(ins) != 1:
        errs.append("工作流须有且仅有 1 个输入节点")
    if len(outs) != 1:
        errs.append("工作流须有且仅有 1 个输出节点")
    if str(nodes[0].type or "").lower() != "input":
        errs.append("第一个节点必须为输入节点")
    if str(nodes[-1].type or "").lower() != "output":
        errs.append("最后一个节点必须为输出节点")
    for idx, node in enumerate(nodes):
        t = str(node.type or "").lower()
        if idx == 0 or idx == len(nodes) - 1:
            continue
        if t in ("input", "output"):
            errs.append("中间步骤不得再添加输入或输出节点")
            break
    return errs


# 语言 code → 人类可读名称映射
_LANG_MAP = {
    "en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语",
    "ar": "阿拉伯语", "pt": "葡萄牙语", "it": "意大利语",
    "zh-CN": "简体中文", "zh-TW": "繁体中文",
}


def _normalize_lang(code_or_label: str) -> str:
    """把语言 code 或 label 统一转为 label。"""
    if code_or_label in _LANG_MAP.values():
        return code_or_label
    return _LANG_MAP.get(code_or_label, code_or_label)


def _resolve_doc_path(doc_id: str, config: SystemConfig) -> Optional[str]:
    """根据文档 ID 解析磁盘路径，支持 session 文件和文档库文件。"""
    lib = get_desktop_local_library()
    if lib:
        pair = lib.get_doc_record(doc_id)
        if pair:
            space_id, _ = pair
            path = lib.resolve_doc_path(space_id, doc_id)
            if path:
                return str(path)
    elif config.database.enabled and is_database_configured(config):
        try:
            from db.library_repository import get_library_doc_by_id

            doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
            if doc and doc.storage_key:
                p = Path(doc.storage_key)
                if p.exists():
                    return str(p)
        except Exception as exc:
            logger.debug("文档库 ID 解析跳过 %s: %s", doc_id, exc)

    # session 文件
    parts = doc_id.split(":", 1)
    if len(parts) == 2 and parts[0] == "session":
        session_id, file_id = parts[1].split("/", 1)
        try:
            session = get_session_by_id(session_id, config=config)
            if session:
                for row in getattr(session, "files", []):
                    if str(row.id) == file_id:
                        p = Path(row.file_path)
                        if p.exists():
                            return str(p)
        except Exception:
            pass

    # 尝试 workspace 目录
    workspace_root = Path(config.work_dir)
    candidates = [
        workspace_root / doc_id,
        workspace_root / "uploads" / doc_id,
        workspace_root / "documents" / doc_id,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)
    return None


def _detect_file_type(name: str) -> FileType:
    """根据文件名推断 FileType。"""
    ext = Path(name).suffix.lower().lstrip(".")
    mapping = {
        "docx": FileType.DOCX,
        "pdf": FileType.PDF,
        "txt": FileType.TXT,
        "md": FileType.MD,
        "markdown": FileType.MD,
        "xlsx": FileType.XLSX,
        "xls": FileType.XLS,
        "csv": FileType.CSV,
        "doc": FileType.DOC,
    }
    return mapping.get(ext, FileType.TXT)


def _make_progress_callback(execution_id: str):
    """生成一个向执行状态写入进度日志的回调。"""

    def callback(progress: int, total: int, message: str, **kwargs):
        if execution_id not in _EXECUTION_STATES:
            return
        state = _EXECUTION_STATES[execution_id]
        file_index = int(state.get("current_file_index") or 1)
        total_files = max(int(state.get("total_files") or 1), 1)
        node_ratio = max(0.0, min(float(progress) / max(total, 1), 1.0))
        overall = int(((file_index - 1) + node_ratio) / total_files * 100)
        state["progress"] = max(0, min(overall, 99 if state.get("status") == "running" else 100))

        node_id = str(kwargs.get("node_id") or "")
        node_title = str(kwargs.get("node_title") or "")
        node_index = int(kwargs.get("node_index") or progress or 0)
        node_status = str(kwargs.get("node_status") or "running")
        node_item_progress = int(kwargs.get("node_progress") if kwargs.get("node_progress") is not None else (100 if node_status == "completed" else 50))

        if node_id or node_title:
            state["current_node_id"] = node_id
            state["current_node_name"] = node_title
            state["current_node_index"] = node_index
            state["total_nodes"] = max(int(state.get("total_nodes") or total or 0), int(total or 0))
            for item in state.get("node_progress", []):
                if (node_id and item.get("id") == node_id) or (not node_id and item.get("title") == node_title):
                    item["status"] = node_status
                    item["progress"] = max(0, min(node_item_progress, 100))
                    item["message"] = message
                    break
        state["logs"].append({"type": "info", "message": message})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states()

    return callback


async def _run_execution(execution_id: str, params: ExecuteRequest):
    """后台执行任务（在线程池中运行，避免阻塞轮询接口）。"""
    await asyncio.to_thread(_run_execution_sync, execution_id, params)


def _run_execution_sync(execution_id: str, params: ExecuteRequest):
    config = get_config()
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        return

    try:
        output_config = _get_output_config(params.nodes)
        output_mode = _normalize_output_mode(output_config.get("outputMode"))
        output_format = output_config.get("outputFormat", "md")
        target_space_id = output_config.get("targetSpaceId")
        save_path = str(output_config.get("savePath") or "").strip()
        naming_rule = output_config.get("namingRule", "{original_name}_out")
        input_config = _get_input_config(params.nodes)

        translation_config = _get_translation_config(params.nodes)
        target_language = _normalize_lang(translation_config.get("targetLanguage", "中文"))

        if not params.docs:
            state["status"] = "failed"
            state["error"] = "请从文档库选择至少一个输入文档"
            state["error_code"] = "VALIDATION_ERROR"
            state["logs"].append({"type": "error", "message": "工作流输入仅支持文档库，请在「文档输入」节点勾选文档"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            return

        if params.localFiles:
            state["logs"].append(
                {
                    "type": "warn",
                    "message": f"已忽略 {len(params.localFiles)} 个本地上传文件；工作流仅支持从文档库读取输入。",
                }
            )

        if output_mode == "library" and not target_space_id:
            state["status"] = "failed"
            state["error"] = "请在「文档输出」节点选择目标文档库"
            state["error_code"] = "VALIDATION_ERROR"
            state["logs"].append({"type": "error", "message": "保存到文档库时请选择目标文档库空间"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            return

        if output_mode == "external" and save_path:
            try:
                dest_probe = Path(save_path)
                if not dest_probe.is_absolute():
                    dest_probe = Path(config.work_dir) / dest_probe
                dest_probe.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                state["status"] = "failed"
                state["error"] = f"无法创建或访问输出目录: {save_path}"
                state["error_code"] = "VALIDATION_ERROR"
                state["logs"].append({"type": "error", "message": state["error"]})
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_execution_states(config)
                return

        if output_mode == "library" and not _library_storage_ready(config):
            msg = (
                "输出到文档库不可用：请选择目标文档库空间后重试。"
                if is_desktop_app()
                else "文档库入库需要 PostgreSQL：请在 .env 中启用 DB_ENABLED 并配置 DATABASE_URL（或其它 DB_*）。当前数据库未就绪，仅能下载/查看本地输出路径。"
            )
            state["logs"].append({"type": "warn", "message": msg})

        saved_local_files: List[Dict[str, Any]] = []

        # ===== 收集源文件列表 =====
        source_files: List[FileInfo] = []

        requested_doc_count = len(params.docs)
        unresolved_doc_ids: List[str] = []

        # 从文档库
        for doc_id in params.docs:
            path = _resolve_doc_path(doc_id, config)
            if path:
                ft = _detect_file_type(Path(path).name)
                source_files.append(FileInfo(path=path, file_type=ft, name=Path(path).name))
            else:
                unresolved_doc_ids.append(doc_id)
                state["logs"].append({"type": "warn", "message": f"文档路径未找到: {doc_id}"})

        if not source_files:
            state["status"] = "failed"
            state["error"] = "没有可处理的文件"
            state["error_code"] = "VALIDATION_ERROR"
            state["logs"].append({"type": "error", "message": "没有可处理的文件"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            return

        state["total_files"] = len(source_files)
        state["logs"].append({"type": "info", "message": f"共 {len(source_files)} 个文件，开始逐个处理..."})

        # ===== 逐文件处理 =====
        all_output_files: List[Dict[str, Any]] = []
        failed_count = len(unresolved_doc_ids)
        skipped_count = 0
        failure_messages: List[str] = []
        if unresolved_doc_ids:
            failure_messages.append(f"{len(unresolved_doc_ids)} 个文档无法解析路径")
        coordinator = WorkflowCoordinator(config)

        for idx, file_info in enumerate(source_files):
            state["current_file_index"] = idx + 1
            state["current_file_name"] = file_info.name
            state["progress"] = int(idx / len(source_files) * 100)
            state["current_node_id"] = ""
            state["current_node_name"] = ""
            state["current_node_index"] = 0
            state["total_nodes"] = len(params.nodes)
            state["node_progress"] = _build_node_progress(params.nodes)
            state["logs"].append(
                {"type": "info", "message": f"[{idx + 1}/{len(source_files)}] 正在处理: {file_info.name}"}
            )
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)

            if not file_info.path or not Path(file_info.path).exists():
                skipped_count += 1
                failed_count += 1
                failure_messages.append(f"文件不存在: {file_info.name}")
                state["logs"].append({"type": "warn", "message": f"  跳过（文件不存在）: {file_info.name}"})
                continue

            task_spec = TaskSpec(
                task_type=TaskType.WORKFLOW_PIPELINE,
                instruction=f"workflow:{params.workflowId}",
                source_files=[file_info],
                session_id=params.sessionId,
                parameters={
                    "workflow_nodes": [n.model_dump() for n in params.nodes],
                    "output_config": {
                        "outputMode": output_mode,
                        "outputFormat": output_format,
                        "targetSpaceId": target_space_id,
                        "namingRule": naming_rule,
                        "targetLanguage": target_language,
                        "savePath": output_config.get("savePath"),
                        "sheetName": output_config.get("sheetName"),
                        "outputEncoding": output_config.get("outputEncoding"),
                        "lineEnding": output_config.get("lineEnding"),
                        "notifyOnComplete": output_config.get("notifyOnComplete"),
                    },
                    "input_config": input_config,
                    "execution_id": execution_id,
                },
            )
            wf_result = coordinator.execute(task_spec, progress_callback=_make_progress_callback(execution_id))
            if not wf_result.success:
                failed_count += 1
                failure_messages.append(str(wf_result.message))
                state["logs"].append({"type": "error", "message": f"  执行失败: {wf_result.message}"})
                continue

            out_item = {}
            if isinstance(wf_result.data, dict):
                out_item = wf_result.data.get("output", {}) or {}
            if not out_item:
                failed_count += 1
                failure_messages.append(f"无输出产物: {file_info.name}")
                state["logs"].append({"type": "warn", "message": f"  无输出产物: {file_info.name}"})
                continue

            all_output_files.append(out_item)
            out_path = out_item.get("path")
            out_name = out_item.get("name", file_info.name)
            if output_mode == "external":
                state["logs"].append(
                    {
                        "type": "done",
                        "message": f"  已输出到本地: {out_path or out_name}"
                        + (f"（{save_path}）" if save_path else ""),
                    }
                )
            else:
                state["logs"].append({"type": "done", "message": f"  已生成: {out_name}"})
            if isinstance(out_item, dict):
                out_item["outputMode"] = output_mode
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)

            if output_mode == "library" and out_path and target_space_id:
                ok_lib, lib_msg = _save_output_to_library(str(out_path), str(target_space_id), config)
                if ok_lib:
                    state["logs"].append({"type": "done", "message": f"  已保存到文档库: {out_name}"})
                else:
                    state["logs"].append({"type": "error", "message": f"  文档库入库失败: {lib_msg}"})
                    failed_count += 1
                    failure_messages.append(lib_msg or "文档库入库失败")

        # ===== 完成 =====
        state["progress"] = 100
        state["output_files"] = all_output_files
        success_count = len(all_output_files)
        total_requested = max(requested_doc_count, len(source_files) + len(unresolved_doc_ids))

        if success_count > 0 and failed_count == 0 and skipped_count == 0:
            state["status"] = "completed"
            state["error"] = None
            state["error_code"] = None
            state["logs"].append({"type": "done", "message": f"全部完成，已处理 {success_count} 个输出文件"})
        elif success_count > 0:
            state["status"] = "partial"
            merged = "；".join(failure_messages[-3:]) if failure_messages else f"{failed_count} 个文件未成功"
            state["error"] = merged
            state["error_code"] = "PARTIAL_SUCCESS"
            state["logs"].append(
                {
                    "type": "warn",
                    "message": f"部分完成：成功 {success_count}/{total_requested}，失败 {failed_count} 个",
                }
            )
        else:
            state["status"] = "failed"
            state["error_code"] = "WORKFLOW_FAILED"
            merged = "；".join(failure_messages[-3:]) if failure_messages else "全部文件处理失败"
            state["error"] = merged
            state["logs"].append({"type": "error", "message": f"执行失败: {merged}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    except Exception as e:
        logger.error(f"执行任务异常: {e}")
        state["status"] = "failed"
        state["error"] = str(e)
        state["error_code"] = "INTERNAL_ERROR"
        state["logs"].append({"type": "error", "message": f"执行异常: {e}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)


def _save_output_to_library(file_path: str, space_id: str, config: SystemConfig) -> Tuple[bool, str]:
    """将输出文件保存到文档库。桌面版写入本地 JSON；服务端写入 PostgreSQL。"""
    lib = get_desktop_local_library()
    if lib:
        try:
            p = Path(file_path)
            if not p.is_file():
                return False, f"输出文件不存在: {file_path}"
            if not lib.get_space(space_id):
                return False, "文档库空间不存在"
            content_bytes = p.read_bytes()
            mime_type, _ = mimetypes.guess_type(p.name)
            lib.add_doc(space_id, p.name, content_bytes, mime_type)
            return True, ""
        except Exception as e:
            logger.warning(f"保存到本地文档库失败: {e}")
            return False, str(e)

    if not (config.database.enabled and is_database_configured(config)):
        return False, "数据库未启用或未配置，无法写入 library_documents"

    try:
        from db.library_repository import add_library_doc, get_library_space_by_id
        import hashlib

        p = Path(file_path)
        if not p.is_file():
            return False, f"输出文件不存在: {file_path}"

        # 与手动上传一致：登记为空间所属用户，否则已登录用户列表会带 user_id 条件，看不到 user_id 为空的记录
        space_row = get_library_space_by_id(space_id, config=config, user_id=None)
        owner_user_id = space_row.user_id if space_row else None

        with open(p, "rb") as f:
            content_bytes = f.read()
        file_size = len(content_bytes)
        file_hash = hashlib.md5(content_bytes).hexdigest()
        safe_name = f"{file_hash}_{p.name}"

        storage_key: Optional[str] = None
        if oss_storage_enabled(config):
            from core.storage import build_blob_name, upload_stream_to_storage
            from io import BytesIO

            blob_name = build_blob_name(space_id, safe_name, prefix=config.storage.object_key_prefix or "workflows")
            storage_key = upload_stream_to_storage(
                BytesIO(content_bytes),
                config=config,
                blob_name=blob_name,
                content_type="application/octet-stream",
            )
        else:
            upload_dir = Path(config.work_dir) / "library" / space_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            storage_key = str(upload_dir / safe_name)
            Path(storage_key).write_bytes(content_bytes)

        add_library_doc(
            space_id=space_id,
            file_name=p.name,
            file_size=file_size,
            config=config,
            user_id=owner_user_id,
            mime_type="application/octet-stream",
            storage_key=storage_key,
            blob_url=storage_key,
        )
        return True, ""
    except Exception as e:
        logger.warning(f"保存到文档库失败: {e}")
        return False, str(e)


# ==================== API 端点 ====================

# ⚠️ 路由顺序很重要：精确路径必须在动态路径 {workflow_id} 之前注册


@router.post("/execute", response_model=Dict[str, str])
async def execute_workflow(request: ExecuteRequest, background_tasks: BackgroundTasks):
    """
    启动工作流执行（逐文件处理）。
    立即返回 execution_id，前端通过 GET /executions/{id} 轮询进度。
    """
    _hydrate_execution_states()
    validation_errors = _validate_execute_request(request)
    if validation_errors:
        raise HTTPException(status_code=400, detail="；".join(validation_errors))

    execution_id = uuid.uuid4().hex

    _EXECUTION_STATES[execution_id] = {
        "status": "running",
        "progress": 0,
        "current_file_index": 0,
        "total_files": 0,
        "current_file_name": "",
        "current_node_id": "",
        "current_node_name": "",
        "current_node_index": 0,
        "total_nodes": len(request.nodes),
        "node_progress": _build_node_progress(request.nodes),
        "logs": [{"type": "info", "message": "任务已启动，正在初始化..."}],
        "output_files": [],
        "error": None,
        "error_code": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _persist_execution_states()

    # 后台运行，不阻塞 HTTP 响应
    background_tasks.add_task(_run_execution, execution_id, request)

    return {"execution_id": execution_id}


# -------- 精确路径端点（必须在 /{workflow_id} 之前） --------


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution_status(execution_id: str):
    """查询工作流执行状态。"""
    _hydrate_execution_states()
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    error_code = state.get("error_code")
    if not error_code and state.get("status") == "failed":
        error_text = str(state.get("error") or "")
        if "没有可处理的文件" in error_text or "缺少" in error_text:
            error_code = "VALIDATION_ERROR"
        else:
            error_code = "WORKFLOW_FAILED"
    return ExecutionResponse(
        execution_id=execution_id,
        status=state["status"],
        progress=state["progress"],
        current_file_index=state["current_file_index"],
        total_files=state["total_files"],
        current_file_name=state["current_file_name"],
        current_node_id=state.get("current_node_id", ""),
        current_node_name=state.get("current_node_name", ""),
        current_node_index=state.get("current_node_index", 0),
        total_nodes=state.get("total_nodes", 0),
        node_progress=state.get("node_progress", []),
        logs=state["logs"],
        output_files=state["output_files"],
        error=state["error"],
        error_code=error_code,
    )


@router.get("/models", response_model=List[Dict[str, str]])
async def list_models():
    """返回可用 LLM 模型列表。"""
    return [
        {"id": "deepseek-chat", "name": "DeepSeek Chat"},
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet"},
    ]


@router.get("/languages", response_model=List[Dict[str, str]])
async def list_languages():
    """返回支持的目标语言列表。"""
    return [
        {"code": "zh", "name": "中文"},
        {"code": "en", "name": "English"},
        {"code": "ja", "name": "日本語"},
        {"code": "ko", "name": "한국어"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "es", "name": "Español"},
        {"code": "ru", "name": "Русский"},
        {"code": "ar", "name": "العربية"},
        {"code": "pt", "name": "Português"},
    ]


@router.get("/output-formats", response_model=List[Dict[str, str]])
async def list_output_formats():
    """返回支持的输出格式列表。"""
    return [
        {"code": "pdf", "name": "PDF"},
        {"code": "md", "name": "Markdown"},
        {"code": "txt", "name": "纯文本"},
        {"code": "xlsx", "name": "Excel"},
    ]


# -------- 用户工作流 CRUD（/{workflow_id} 必须在最后） --------


class SaveWorkflowRequest(BaseModel):
    id: str = Field(..., description="工作流 ID（唯一标识，新建时由前端生成）")
    name: str = Field(..., description="工作流名称")
    icon: str = Field("🔧", description="图标 emoji")
    type: str = Field("custom", description="类型（保留字段，均为 custom）")
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="节点列表（含 configValues 等完整配置）"
    )
    config: Dict[str, Any] = Field(default_factory=dict, description="全局配置")


@router.get("", response_model=Dict[str, Any])
async def list_user_workflows():
    """返回用户工作流列表；首次使用时自动写入示例工作流。"""
    seed_starter_workflows_if_empty()
    return {"workflows": list_workflows()}


@router.post("", response_model=Dict[str, Any])
async def save_user_workflow(request: SaveWorkflowRequest):
    """保存（新建或更新）用户工作流。"""
    wf = save_workflow(
        workflow_id=request.id,
        name=request.name,
        icon=request.icon,
        nodes=request.nodes,
        config_data=request.config,
    )
    return wf


@router.get("/{workflow_id}", response_model=Dict[str, Any])
async def get_single_workflow(workflow_id: str):
    """获取指定工作流的完整配置（含节点和 config）。"""
    wf = get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


@router.delete("/{workflow_id}", response_model=Dict[str, bool])
async def delete_user_workflow(workflow_id: str):
    """删除指定用户工作流。"""
    success = delete_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return True

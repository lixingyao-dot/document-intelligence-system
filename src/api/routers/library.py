"""文档库 API 路由"""
from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import load_config
from core.storage import (
    build_blob_name,
    delete_file_from_storage,
    download_file_to_local,
    upload_stream_to_storage,
    oss_storage_enabled,
)
from db.auth_repository import resolve_user_from_authorization
from db.library_repository import (
    LibraryDocRow,
    LibrarySpaceRow,
    add_library_doc,
    create_library_space,
    delete_library_doc,
    delete_library_space,
    get_library_doc_by_id,
    get_library_docs,
    get_library_space_by_id,
    get_library_spaces,
)


router = APIRouter(prefix="/api/library", tags=["文档库管理"])

# 文档库文件上传目录
LIBRARY_UPLOAD_DIR = Path("workspace/library")
LIBRARY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------

class SpaceItem(BaseModel):
    id: str
    name: str
    icon: str
    description: Optional[str] = None
    doc_count: int
    created_at: str
    updated_at: str


class SpaceListResponse(BaseModel):
    spaces: List[SpaceItem]


class DocItem(BaseModel):
    id: str
    space_id: str
    file_name: str
    file_size: int
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    storage_key: Optional[str] = None
    blob_url: Optional[str] = None
    created_at: str
    updated_at: str


class DocListResponse(BaseModel):
    docs: List[DocItem]
    total: int


class ExportBatchRequest(BaseModel):
    doc_ids: List[str] = Field(default_factory=list, min_length=1)
    archive_name: Optional[str] = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _resolve_user(authorization: Optional[str], cfg):
    if not authorization:
        if cfg.auth.require_auth:
            raise HTTPException(status_code=401, detail="需要登录后访问")
        return None
    try:
        return resolve_user_from_authorization(authorization, cfg, required=True)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def _space_to_dict(s: LibrarySpaceRow) -> Dict[str, Any]:
    def _fmt(dt):
        if not dt:
            return ""
        iso = dt.isoformat()
        return iso if iso.endswith("Z") else iso.replace("+00:00", "Z")

    return {
        "id": s.id,
        "name": s.name,
        "icon": s.icon,
        "description": s.description,
        "doc_count": s.doc_count,
        "created_at": _fmt(s.created_at),
        "updated_at": _fmt(s.updated_at),
    }


def _doc_to_dict(d: LibraryDocRow) -> Dict[str, Any]:
    def _fmt(dt):
        if not dt:
            return ""
        iso = dt.isoformat()
        return iso if iso.endswith("Z") else iso.replace("+00:00", "Z")

    return {
        "id": d.id,
        "space_id": d.space_id,
        "file_name": d.file_name,
        "file_size": d.file_size,
        "mime_type": d.mime_type,
        "file_extension": d.file_extension,
        "storage_key": d.storage_key,
        "blob_url": d.blob_url,
        "created_at": _fmt(d.created_at),
        "updated_at": _fmt(d.updated_at),
    }


def _compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _resolve_library_doc_path(doc: LibraryDocRow, cfg) -> Path:
    """解析文档在磁盘上的路径（与单文件下载逻辑一致）。"""
    storage_key = doc.storage_key
    blob_url = doc.blob_url
    file_path: Optional[Path] = None

    if storage_key and oss_storage_enabled(cfg):
        cache_path = Path(cfg.temp_dir) / "oss_cache" / storage_key
        try:
            file_path = Path(download_file_to_local(storage_key, cache_path, config=cfg))
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"文件不存在: {exc}") from exc

    if not file_path and blob_url:
        local_path = Path(blob_url)
        if local_path.exists():
            file_path = local_path

    if not file_path and storage_key:
        local_path = Path(storage_key)
        if local_path.exists():
            file_path = local_path

    if not file_path or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {doc.file_name}")
    return file_path


def _unique_archive_entry_name(file_name: str, used: Dict[str, int]) -> str:
    safe = Path(file_name or "unnamed").name
    if safe not in used:
        used[safe] = 0
        return safe
    used[safe] += 1
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    return f"{stem}_{used[safe]}{suffix}"


def _build_docs_zip(
    entries: List[Tuple[str, Path]],
    *,
    skipped: List[str],
) -> BytesIO:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names: Dict[str, int] = {}
        for file_name, path in entries:
            arcname = _unique_archive_entry_name(file_name, used_names)
            zf.write(path, arcname=arcname)
        if skipped:
            manifest = "以下文档未能导出（文件缺失或无权限）：\n" + "\n".join(skipped)
            zf.writestr("_export_skipped.txt", manifest.encode("utf-8"))
    buffer.seek(0)
    return buffer


def _zip_content_disposition(filename: str) -> str:
    ascii_name = "".join(c if c.isascii() and c not in '"\\' else "_" for c in filename) or "export.zip"
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.2f} GB"


# ---------------------------------------------------------------------------
# 空间管理
# ---------------------------------------------------------------------------

@router.get("/spaces", response_model=SpaceListResponse)
async def list_spaces(authorization: Optional[str] = Header(default=None)):
    """获取所有文档空间列表"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    spaces = get_library_spaces(config=cfg, user_id=user.id if user else None)
    return SpaceListResponse(spaces=[_space_to_dict(s) for s in spaces])


@router.post("/spaces", response_model=SpaceItem)
async def create_space(
    body: Dict[str, Any],
    authorization: Optional[str] = Header(default=None),
):
    """创建新文档空间"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="空间名称不能为空")

    icon = body.get("icon", "📁")
    description = body.get("description")

    space = create_library_space(
        name=name,
        icon=icon,
        description=description,
        config=cfg,
        user_id=user.id if user else None,
    )
    return _space_to_dict(space)


@router.put("/spaces/{space_id}", response_model=SpaceItem)
async def update_space(
    space_id: str,
    body: Dict[str, Any],
    authorization: Optional[str] = Header(default=None),
):
    """更新文档空间"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    space = get_library_space_by_id(space_id, config=cfg, user_id=user.id if user else None)
    if not space:
        raise HTTPException(status_code=404, detail="空间不存在")

    from db.library_repository import update_library_space
    result = update_library_space(
        space_id=space_id,
        name=body.get("name"),
        icon=body.get("icon"),
        description=body.get("description"),
        config=cfg,
        user_id=user.id if user else None,
    )
    if not result:
        raise HTTPException(status_code=404, detail="空间不存在")
    return _space_to_dict(result)


@router.delete("/spaces/{space_id}")
async def delete_space(
    space_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """删除文档空间（同时删除空间下所有文档）"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    space = get_library_space_by_id(space_id, config=cfg, user_id=user.id if user else None)
    if not space:
        raise HTTPException(status_code=404, detail="空间不存在")

    # 删除空间下所有文档的 OSS 对象
    docs = get_library_docs(space_id, config=cfg, user_id=user.id if user else None)
    for doc in docs:
        if doc.storage_key:
            delete_file_from_storage(doc.storage_key, config=cfg)

    success = delete_library_space(space_id, config=cfg, user_id=user.id if user else None)
    return {"success": success}


# ---------------------------------------------------------------------------
# 文档管理
# ---------------------------------------------------------------------------

@router.get("/spaces/{space_id}/docs", response_model=DocListResponse)
async def list_docs(
    space_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """获取空间下所有文档"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    space = get_library_space_by_id(space_id, config=cfg, user_id=user.id if user else None)
    if not space:
        raise HTTPException(status_code=404, detail="空间不存在")

    docs = get_library_docs(space_id, config=cfg, user_id=user.id if user else None)
    return DocListResponse(
        docs=[_doc_to_dict(d) for d in docs],
        total=len(docs),
    )


@router.post("/spaces/{space_id}/docs", response_model=DocItem)
async def upload_doc(
    space_id: str,
    file: UploadFile,
    authorization: Optional[str] = Header(default=None),
):
    """上传文档到指定空间"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    space = get_library_space_by_id(space_id, config=cfg, user_id=user.id if user else None)
    if not space:
        raise HTTPException(status_code=404, detail="空间不存在")

    file_name = file.filename or "unnamed"
    content = await file.read()
    file_size = len(content)

    # 读取内容用于计算 hash
    file_hash = _compute_file_hash(content)

    storage_key = None
    if oss_storage_enabled(cfg):
        blob_name = build_blob_name(
            space_id,
            f"{file_hash}_{file_name}",
            prefix=cfg.storage.object_key_prefix,
        )
        storage_key = upload_stream_to_storage(
            BytesIO(content),
            config=cfg,
            blob_name=blob_name,
            content_type=file.content_type,
        )
        if not storage_key:
            raise HTTPException(status_code=502, detail="OSS 上传失败")
    else:
        # 本地存储
        safe_name = f"{file_hash}_{file_name}"
        file_path = LIBRARY_UPLOAD_DIR / space_id / safe_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        storage_key = str(file_path)

    doc = add_library_doc(
        space_id=space_id,
        file_name=file_name,
        file_size=file_size,
        config=cfg,
        user_id=user.id if user else None,
        mime_type=file.content_type,
        storage_key=storage_key,
        blob_url=storage_key,
    )
    return _doc_to_dict(doc)


@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """删除文档"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    doc = get_library_doc_by_id(doc_id, config=cfg, user_id=user.id if user else None)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 删除 OSS 对象
    if doc.storage_key:
        delete_file_from_storage(doc.storage_key, config=cfg)

    success = delete_library_doc(doc_id, config=cfg, user_id=user.id if user else None)
    return {"success": success}


@router.post("/docs/delete-batch")
async def delete_docs_batch(
    body: Dict[str, Any],
    authorization: Optional[str] = Header(default=None),
):
    """批量删除文档"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    doc_ids: List[str] = body.get("doc_ids", [])
    if not doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids 不能为空")

    results = []
    for doc_id in doc_ids:
        doc = get_library_doc_by_id(doc_id, config=cfg, user_id=user.id if user else None)
        if doc and doc.storage_key:
            delete_file_from_storage(doc.storage_key, config=cfg)
        success = delete_library_doc(doc_id, config=cfg, user_id=user.id if user else None)
        results.append({"doc_id": doc_id, "success": success})

    return {"results": results}


@router.get("/docs/{doc_id}/download")
async def download_doc(
    doc_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """下载文档"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)

    doc = get_library_doc_by_id(doc_id, config=cfg, user_id=user.id if user else None)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    file_path = _resolve_library_doc_path(doc, cfg)
    mime_type = doc.mime_type or "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        filename=doc.file_name,
        media_type=mime_type,
    )


@router.post("/docs/export-batch")
async def export_docs_batch(
    body: ExportBatchRequest,
    authorization: Optional[str] = Header(default=None),
):
    """批量导出文档为 ZIP 压缩包。"""
    cfg = load_config()
    user = _resolve_user(authorization, cfg)
    user_id = user.id if user else None

    doc_ids = [str(d).strip() for d in body.doc_ids if str(d).strip()]
    if not doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids 不能为空")

    entries: List[Tuple[str, Path]] = []
    skipped: List[str] = []

    for doc_id in doc_ids:
        doc = get_library_doc_by_id(doc_id, config=cfg, user_id=user_id)
        if not doc:
            skipped.append(f"{doc_id}（文档不存在）")
            continue
        try:
            path = _resolve_library_doc_path(doc, cfg)
            entries.append((doc.file_name or path.name, path))
        except HTTPException:
            skipped.append(f"{doc.file_name or doc_id}（文件不存在）")

    if not entries:
        raise HTTPException(status_code=404, detail="没有可导出的文件")

    zip_buffer = _build_docs_zip(entries, skipped=skipped)
    space_label = (body.archive_name or "documents").strip() or "documents"
    if not space_label.lower().endswith(".zip"):
        space_label = f"{space_label}.zip"
    safe_label = Path(space_label).name

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _zip_content_disposition(safe_label)},
    )

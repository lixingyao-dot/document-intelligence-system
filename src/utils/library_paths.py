"""文档库路径解析与输出入库（对话 / 工作流共用）。"""
from __future__ import annotations

import hashlib
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import SystemConfig
from utils.desktop_runtime import get_desktop_local_library, is_desktop_app


def resolve_library_doc_path(doc_id: str, config: SystemConfig) -> Optional[str]:
    """根据文档库 doc_id 解析本地可读路径。"""
    if not doc_id:
        return None

    lib = get_desktop_local_library()
    if lib:
        pair = lib.get_doc_record(doc_id)
        if pair:
            space_id, _ = pair
            path = lib.resolve_doc_path(space_id, doc_id)
            if path:
                return str(path)
    else:
        try:
            from db.database import is_database_configured
            from db.library_repository import get_library_doc_by_id
        except ImportError:
            is_database_configured = lambda _cfg: False  # type: ignore
            get_library_doc_by_id = None  # type: ignore

        if config.database.enabled and is_database_configured(config) and get_library_doc_by_id:
            doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
            if doc and doc.storage_key:
                p = Path(doc.storage_key)
                if p.exists():
                    return str(p)

    workspace_root = Path(config.work_dir)
    for candidate in (
        workspace_root / "library" / doc_id,
        workspace_root / doc_id,
    ):
        if candidate.exists():
            return str(candidate)
    return None


def enrich_files_with_library_paths(
    files: Optional[List[Dict[str, Any]]],
    config: SystemConfig,
) -> List[Dict[str, Any]]:
    """为携带 library_doc_id 的文件条目补全 storage_key / file_path。"""
    if not files:
        return []
    enriched: List[Dict[str, Any]] = []
    for raw in files:
        item = dict(raw or {})
        doc_id = str(item.get("library_doc_id") or item.get("doc_id") or "").strip()
        if not doc_id:
            enriched.append(item)
            continue
        path = resolve_library_doc_path(doc_id, config)
        if not path:
            enriched.append(item)
            continue
        p = Path(path)
        item["library_doc_id"] = doc_id
        item["storage_key"] = path
        item["file_path"] = path
        if not item.get("file_name"):
            item["file_name"] = p.name
        if not item.get("file_size") and p.is_file():
            item["file_size"] = p.stat().st_size
        item.setdefault("is_selected", True)
        enriched.append(item)
    return enriched


def save_file_to_library_space(
    file_path: str,
    space_id: str,
    config: SystemConfig,
    *,
    display_name: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    将磁盘文件写入文档库空间。
    返回 (成功, 错误信息, 新文档 doc_id)。
    """
    lib = get_desktop_local_library()
    p = Path(file_path)
    if not p.is_file():
        return False, f"输出文件不存在: {file_path}", None
    out_name = display_name or p.name

    if lib:
        try:
            if not lib.get_space(space_id):
                return False, "文档库空间不存在", None
            content_bytes = p.read_bytes()
            mime_type, _ = mimetypes.guess_type(out_name)
            doc = lib.add_doc(space_id, out_name, content_bytes, mime_type)
            doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
            return True, "", str(doc_id) if doc_id else None
        except Exception as exc:
            return False, str(exc), None

    try:
        from db.database import is_database_configured
        from db.library_repository import add_library_doc, get_library_space_by_id
        from core.storage import build_blob_name, oss_storage_enabled, upload_stream_to_storage
    except ImportError as exc:
        return False, str(exc), None

    if not (config.database.enabled and is_database_configured(config)):
        return False, "文档库需要数据库配置", None

    try:
        space_row = get_library_space_by_id(space_id, config=config, user_id=None)
        owner_user_id = space_row.user_id if space_row else None
        content_bytes = p.read_bytes()
        file_size = len(content_bytes)
        file_hash = hashlib.md5(content_bytes).hexdigest()
        safe_name = f"{file_hash}_{out_name}"

        storage_key: Optional[str] = None
        if oss_storage_enabled(config):
            blob_name = build_blob_name(
                space_id,
                safe_name,
                prefix=config.storage.object_key_prefix or "outputs",
            )
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

        doc = add_library_doc(
            space_id=space_id,
            file_name=out_name,
            file_size=file_size,
            config=config,
            user_id=owner_user_id,
            mime_type="application/octet-stream",
            storage_key=storage_key,
            blob_url=storage_key,
        )
        doc_id = getattr(doc, "id", None)
        return True, "", str(doc_id) if doc_id else None
    except Exception as exc:
        return False, str(exc), None


def persist_generated_files_to_library(
    generated_files: List[Dict[str, Any]],
    space_id: str,
    config: SystemConfig,
) -> List[Dict[str, Any]]:
    """将会话生成文件复制到文档库，返回带 library_doc_id 的条目列表。"""
    if not space_id or not generated_files:
        return []
    saved: List[Dict[str, Any]] = []
    for gf in generated_files:
        path = str(gf.get("file_path") or gf.get("path") or "").strip()
        if not path:
            continue
        name = str(gf.get("file_name") or gf.get("name") or Path(path).name)
        ok, err, doc_id = save_file_to_library_space(path, space_id, config, display_name=name)
        if not ok:
            continue
        saved.append(
            {
                **gf,
                "file_name": name,
                "library_doc_id": doc_id,
                "library_space_id": space_id,
                "source": "library",
            }
        )
    return saved

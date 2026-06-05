"""本地文件存储（桌面默认）。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Optional

from config import SystemConfig, get_config


def build_blob_name(session_id: str, file_name: str, prefix: str = "sessions") -> str:
    """生成相对存储键：{prefix}/{session_id}/{file_name}。"""
    safe_name = Path(file_name).name
    safe_session = str(session_id).strip().strip("/")
    safe_prefix = str(prefix).strip().strip("/") or "sessions"
    return f"{safe_prefix}/{safe_session}/{safe_name}"


def oss_storage_enabled(config: Optional[SystemConfig] = None) -> bool:
    return False


def _storage_root(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    return Path(cfg.work_dir) / "storage"


def _resolve_path(blob_name: str, config: Optional[SystemConfig] = None) -> Path:
    p = Path(blob_name)
    if p.is_absolute():
        return p
    return _storage_root(config) / blob_name


def upload_file_to_storage(
    local_path: str | Path,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    path_obj = Path(local_path)
    key = blob_name or path_obj.name
    dest = _resolve_path(key, config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path_obj, dest)
    return key


def upload_stream_to_storage(
    stream: BinaryIO,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    if not blob_name:
        raise ValueError("blob_name 不能为空")
    dest = _resolve_path(blob_name, config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(stream.read())
    return blob_name


def download_file_to_local(
    blob_name: str,
    destination: str | Path,
    config: Optional[SystemConfig] = None,
) -> Path:
    src = _resolve_path(blob_name, config)
    if not src.is_file():
        alt = Path(blob_name)
        if alt.is_file():
            src = alt
        else:
            raise FileNotFoundError(blob_name)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def delete_file_from_storage(blob_name: Optional[str], config: Optional[SystemConfig] = None) -> bool:
    if not blob_name:
        return False
    p = _resolve_path(blob_name, config)
    if p.is_file():
        p.unlink()
        return True
    return False


class _DisabledStorageBackend:
    enabled = False


def get_storage_backend(config: Optional[SystemConfig] = None) -> _DisabledStorageBackend:
    return _DisabledStorageBackend()

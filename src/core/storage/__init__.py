"""文件存储适配层（桌面：本地磁盘）。"""

from .local_storage import (
    build_blob_name,
    delete_file_from_storage,
    download_file_to_local,
    get_storage_backend,
    oss_storage_enabled,
    upload_file_to_storage,
    upload_stream_to_storage,
)

__all__ = [
    "build_blob_name",
    "delete_file_from_storage",
    "download_file_to_local",
    "get_storage_backend",
    "oss_storage_enabled",
    "upload_file_to_storage",
    "upload_stream_to_storage",
]

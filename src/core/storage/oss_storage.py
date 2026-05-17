"""阿里云 OSS 对象存储：对象键、上传/下载/删除与项目各路由对接。"""
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional

from config import SystemConfig, get_config

try:
    import oss2
    from oss2.exceptions import NoSuchKey
except Exception:  # pragma: no cover
    oss2 = None

    class NoSuchKey(Exception):
        pass


def build_blob_name(session_id: str, file_name: str, prefix: str = "sessions") -> str:
    """生成 OSS 对象键：{prefix}/{session_id}/{file_name}。"""
    safe_name = Path(file_name).name
    safe_session = str(session_id).strip().strip("/")
    safe_prefix = str(prefix).strip().strip("/") or "sessions"
    return f"{safe_prefix}/{safe_session}/{safe_name}"


class AliyunOSSStorage:
    """面向项目的 OSS 访问封装。"""

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self._bucket: Optional["oss2.Bucket"] = None

    @property
    def enabled(self) -> bool:
        s = self.config.storage
        return bool(
            s.enabled
            and s.provider == "aliyun_oss"
            and s.oss_endpoint
            and s.oss_access_key_id
            and s.oss_access_key_secret
            and s.oss_bucket
        )

    def _get_bucket(self) -> "oss2.Bucket":
        if not self.enabled:
            raise RuntimeError("阿里云 OSS 未启用或配置不完整")
        if oss2 is None:
            raise RuntimeError("未安装 oss2，无法启用阿里云 OSS（pip install oss2）")
        if self._bucket is not None:
            return self._bucket
        s = self.config.storage
        auth = oss2.Auth(s.oss_access_key_id, s.oss_access_key_secret)
        ep = s.oss_endpoint.strip()
        if not ep.startswith("http://") and not ep.startswith("https://"):
            ep = "https://" + ep
        self._bucket = oss2.Bucket(auth, ep, s.oss_bucket)
        return self._bucket

    def upload_file(self, local_path: Path, blob_name: str, content_type: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        bucket = self._get_bucket()
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        with local_path.open("rb") as handle:
            bucket.put_object(blob_name, handle, headers=headers if headers else None)
        return blob_name

    def upload_stream(self, stream: BinaryIO, blob_name: str, content_type: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        bucket = self._get_bucket()
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        bucket.put_object(blob_name, stream, headers=headers if headers else None)
        return blob_name

    def download_to_path(self, blob_name: str, destination: Path) -> Path:
        if not self.enabled:
            raise RuntimeError("阿里云 OSS 未启用")
        bucket = self._get_bucket()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = bucket.get_object(blob_name)
            with destination.open("wb") as handle:
                handle.write(result.read())
        except NoSuchKey as exc:
            raise FileNotFoundError(blob_name) from exc
        return destination

    def delete_file(self, blob_name: str) -> bool:
        if not self.enabled:
            return False
        bucket = self._get_bucket()
        try:
            bucket.delete_object(blob_name)
            return True
        except Exception:
            return False


def get_storage_backend(config: Optional[SystemConfig] = None) -> AliyunOSSStorage:
    return AliyunOSSStorage(config=config)


def oss_storage_enabled(config: Optional[SystemConfig] = None) -> bool:
    """是否已正确配置并启用阿里云 OSS。"""
    cfg = config or get_config()
    return get_storage_backend(cfg).enabled


def upload_file_to_storage(
    local_path: str | Path,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    path_obj = Path(local_path)
    storage = get_storage_backend(config)
    if not storage.enabled:
        return None
    resolved_blob_name = blob_name or path_obj.name
    return storage.upload_file(path_obj, resolved_blob_name, content_type=content_type)


def upload_stream_to_storage(
    stream: BinaryIO,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    storage = get_storage_backend(config)
    if not storage.enabled:
        return None
    if not blob_name:
        raise ValueError("blob_name 不能为空")
    return storage.upload_stream(stream, blob_name, content_type=content_type)


def download_file_to_local(
    blob_name: str,
    destination: str | Path,
    config: Optional[SystemConfig] = None,
) -> Path:
    storage = get_storage_backend(config)
    return storage.download_to_path(blob_name, Path(destination))


def delete_file_from_storage(blob_name: Optional[str], config: Optional[SystemConfig] = None) -> bool:
    if not blob_name:
        return False
    storage = get_storage_backend(config)
    return storage.delete_file(blob_name)

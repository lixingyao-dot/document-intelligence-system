"""
文件上传处理模块
处理文件上传、类型检测和元数据提取
"""
import os
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

from config import SystemConfig, get_config
from core.orchestrator.task_spec import FileInfo, FileType
from utils.logger import get_logger


@dataclass
class UploadResult:
    """上传结果"""
    success: bool
    message: str
    file_info: Optional[FileInfo] = None


class FileUploader:
    """
    文件上传处理器
    支持本地文件上传、类型检测和元数据提取
    """

    # 文件扩展名到FileType的映射
    EXTENSION_MAP = {
        ".docx": FileType.DOCX,
        ".doc": FileType.DOC,
        ".pdf": FileType.PDF,
        ".txt": FileType.TXT,
        ".md": FileType.MD,
        ".xlsx": FileType.XLSX,
        ".xls": FileType.XLS,
        ".csv": FileType.CSV,
    }

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        self.uploaded_files: List[FileInfo] = []

    def upload(self, file_path: str) -> UploadResult:
        """
        上传文件
        验证文件并提取元数据
        """
        path = Path(file_path)

        # 检查文件是否存在
        if not path.exists():
            return UploadResult(
                success=False,
                message=f"文件不存在: {file_path}"
            )

        # 检查是否是文件
        if not path.is_file():
            return UploadResult(
                success=False,
                message=f"路径不是文件: {file_path}"
            )

        # 获取文件扩展名
        ext = path.suffix.lower()

        # 检查是否支持的文件类型
        if ext not in self.EXTENSION_MAP:
            supported = ", ".join(self.EXTENSION_MAP.keys())
            return UploadResult(
                success=False,
                message=f"不支持的文件类型: {ext}。支持的类型: {supported}"
            )

        # 检查文件大小
        file_size = path.stat().st_size
        max_size = self.config.file.max_file_size_mb * 1024 * 1024
        if file_size > max_size:
            return UploadResult(
                success=False,
                message=f"文件过大: {file_size / 1024 / 1024:.2f}MB > {self.config.file.max_file_size_mb}MB"
            )

        # 创建文件信息
        file_type = self.EXTENSION_MAP[ext]
        file_info = FileInfo(
            path=str(path.absolute()),
            file_type=file_type,
            name=path.name,
            size=file_size,
            metadata={
                "extension": ext,
                "parent_dir": str(path.parent),
                "created_time": path.stat().st_ctime,
                "modified_time": path.stat().st_mtime,
            }
        )

        self.uploaded_files.append(file_info)
        self.logger.info(f"文件上传成功: {file_info.name}")

        return UploadResult(
            success=True,
            message=f"文件上传成功: {file_info.name}",
            file_info=file_info
        )

    def upload_multiple(self, file_paths: List[str]) -> List[UploadResult]:
        """批量上传文件"""
        results = []
        for path in file_paths:
            result = self.upload(path)
            results.append(result)
        return results

    def get_uploaded_files(self) -> List[FileInfo]:
        """获取已上传的文件列表"""
        return self.uploaded_files

    def clear_uploaded_files(self):
        """清除已上传的文件列表"""
        self.uploaded_files.clear()

    def get_files_by_type(self, file_type: FileType) -> List[FileInfo]:
        """根据类型获取已上传的文件"""
        return [f for f in self.uploaded_files if f.file_type == file_type]

    @classmethod
    def detect_file_type(cls, file_path: str) -> FileType:
        """检测文件类型"""
        ext = Path(file_path).suffix.lower()
        return cls.EXTENSION_MAP.get(ext, FileType.TXT)

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """检查文件是否支持"""
        ext = Path(file_path).suffix.lower()
        return ext in cls.EXTENSION_MAP

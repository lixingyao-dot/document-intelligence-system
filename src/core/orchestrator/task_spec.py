"""
任务规格定义
定义任务类型、数据结构和任务规格类
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


class TaskType(Enum):
    """任务类型枚举"""
    DEFAULT_CONVERSATION = "default_conversation"  # 默认对话模式
    DOCUMENT_UNDERSTANDING = "document_understanding"  # 文档理解模式
    DOCUMENT_EDITING = "document_editing"  # 文档编辑模式
    ENTITY_EXTRACTION = "entity_extraction"  # 实体提取模式
    TABLE_FILLING = "table_filling"  # 表格填表模式
    WORKFLOW_PIPELINE = "workflow_pipeline"  # 工作流节点编排模式


class FileType(Enum):
    """支持的文件类型"""
    DOCX = "docx"
    PDF = "pdf"
    TXT = "txt"
    MD = "md"
    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"
    DOC = "doc"


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    file_type: FileType
    name: str = ""
    size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            self.name = Path(self.path).name


@dataclass
class TaskSpec:
    """
    任务规格类
    包含执行任务所需的所有信息
    """
    task_type: TaskType
    instruction: str = ""  # 用户指令
    source_files: List[FileInfo] = field(default_factory=list)  # 源文件（数据源）
    template_file: Optional[FileInfo] = None  # 模板文件
    output_file: Optional[str] = None  # 输出文件路径
    parameters: Dict[str, Any] = field(default_factory=dict)  # 额外参数
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # 对话历史
    session_id: Optional[str] = None  # 会话ID

    def get_source_by_type(self, file_type: FileType) -> List[FileInfo]:
        """根据文件类型获取源文件"""
        return [f for f in self.source_files if f.file_type == file_type]

    def has_document(self) -> bool:
        """检查是否有文档文件"""
        doc_types = [FileType.DOCX, FileType.PDF, FileType.TXT, FileType.MD]
        return any(f.file_type in doc_types for f in self.source_files)

    def has_table(self) -> bool:
        """检查是否有表格文件"""
        table_types = [FileType.XLSX, FileType.XLS, FileType.CSV]
        return any(f.file_type in table_types for f in self.source_files)

    def validate(self) -> tuple[bool, str]:
        """
        验证任务规格
        返回: (是否有效, 错误信息)
        """
        if self.task_type == TaskType.DEFAULT_CONVERSATION:
            return True, ""

        # 文档理解模式允许空文件，用户可以先进入再上传
        if self.task_type == TaskType.DOCUMENT_UNDERSTANDING:
            return True, ""

        if not self.source_files:
            return False, "缺少源文件"

        # 检查源文件路径是否有效
        for f in self.source_files:
            if not f.path or not f.path.strip():
                return False, f"源文件路径为空: {f.name}"

        if self.task_type == TaskType.DOCUMENT_EDITING:
            docx_files = self.get_source_by_type(FileType.DOCX)
            if not docx_files:
                return False, "文档编辑模式需要提供 Word 文档 (docx)"

        elif self.task_type == TaskType.ENTITY_EXTRACTION:
            if not self.has_document():
                return False, "实体提取模式需要提供非结构化文档 (docx/pdf/txt/md)"
            if not self.template_file:
                return False, "实体提取模式需要提供模板文件 (xlsx)"
            if not self.template_file.path or not self.template_file.path.strip():
                return False, "模板文件路径为空"

        elif self.task_type == TaskType.TABLE_FILLING:
            if not self.has_table():
                return False, "表格填表模式需要提供 Excel 文件 (xlsx/xls)"
        elif self.task_type == TaskType.WORKFLOW_PIPELINE:
            if not self.source_files:
                return False, "工作流编排模式需要提供至少一个源文件"

        return True, ""


def detect_task_type_from_files(files: List[FileInfo]) -> TaskType:
    """
    根据文件类型自动检测任务类型
    """
    has_doc = any(f.file_type in [FileType.DOCX, FileType.PDF, FileType.TXT, FileType.MD] for f in files)
    has_table = any(f.file_type in [FileType.XLSX, FileType.XLS, FileType.CSV] for f in files)

    if has_doc and has_table:
        return TaskType.ENTITY_EXTRACTION
    elif has_table:
        return TaskType.TABLE_FILLING
    elif has_doc:
        return TaskType.DOCUMENT_UNDERSTANDING

    return TaskType.DEFAULT_CONVERSATION

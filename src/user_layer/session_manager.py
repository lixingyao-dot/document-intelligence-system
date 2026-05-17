"""
会话管理器
管理用户会话状态，包括工作模式、已上传的文件等
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum

from core.orchestrator.task_spec import TaskType, FileInfo


class CommandType(Enum):
    """命令类型"""
    TEXT = "text"  # 普通文本输入
    MENU = "menu"  # 查看菜单
    SELECT_MODE = "select_mode"  # 选择工作模式
    UPLOAD_DATA = "upload_data"  # 上传原数据
    UPLOAD_TEMPLATE = "upload_template"  # 上传模板
    SHOW_STATUS = "status"  # 显示当前状态
    RESET = "reset"  # 重置会话


@dataclass
class SessionState:
    """会话状态"""
    task_type: TaskType = TaskType.DEFAULT_CONVERSATION
    data_files: list[FileInfo] = field(default_factory=list)
    template_file: Optional[FileInfo] = None
    custom_instruction: str = ""


class SessionManager:
    """
    会话管理器
    维护用户会话状态，支持命令式交互
    """

    WORK_MODES = {
        "document": TaskType.DOCUMENT_UNDERSTANDING,
        "document_understanding": TaskType.DOCUMENT_UNDERSTANDING,
        "文档理解": TaskType.DOCUMENT_UNDERSTANDING,
        "editing": TaskType.DOCUMENT_EDITING,
        "document_editing": TaskType.DOCUMENT_EDITING,
        "agent_a": TaskType.DOCUMENT_EDITING,
        "agent a": TaskType.DOCUMENT_EDITING,
        "文档编辑": TaskType.DOCUMENT_EDITING,
        "extract": TaskType.ENTITY_EXTRACTION,
        "entity_extraction": TaskType.ENTITY_EXTRACTION,
        "实体提取": TaskType.ENTITY_EXTRACTION,
        "fill": TaskType.TABLE_FILLING,
        "table_filling": TaskType.TABLE_FILLING,
        "agent_d": TaskType.TABLE_FILLING,
        "agent d": TaskType.TABLE_FILLING,
        "表格填表": TaskType.TABLE_FILLING,
        "conversation": TaskType.DEFAULT_CONVERSATION,
        "default_conversation": TaskType.DEFAULT_CONVERSATION,
        "对话": TaskType.DEFAULT_CONVERSATION,
    }

    MODE_DISPLAY_NAMES = {
        TaskType.DEFAULT_CONVERSATION: "对话模式",
        TaskType.DOCUMENT_UNDERSTANDING: "文档理解",
        TaskType.DOCUMENT_EDITING: "文档编辑",
        TaskType.ENTITY_EXTRACTION: "实体提取",
        TaskType.TABLE_FILLING: "表格填表",
    }

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get_session(self, session_id: str) -> SessionState:
        """获取或创建会话状态"""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> SessionState:
        """重置会话状态"""
        self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def parse_command(self, user_input: str) -> tuple[CommandType, str, Dict[str, Any]]:
        """
        解析用户输入
        返回: (命令类型, 清理后的文本, 附加数据)
        """
        text = user_input.strip()

        # 小写版本用于匹配
        text_lower = text.lower()

        # menu 命令
        if text_lower == "menu":
            return CommandType.MENU, "", {}

        # status 命令
        if text_lower in ("status", "状态"):
            return CommandType.SHOW_STATUS, "", {}

        # reset 命令
        if text_lower in ("reset", "重置"):
            return CommandType.RESET, "", {}

        # select <模式> 命令
        if text_lower.startswith("select "):
            mode = text[7:].strip()
            return CommandType.SELECT_MODE, mode, {}

        # upload data <路径> 命令
        if text_lower.startswith("upload data "):
            path = text[12:].strip().strip('"\'')
            return CommandType.UPLOAD_DATA, path, {}

        # upload template <路径> 命令
        if text_lower.startswith("upload template "):
            path = text[16:].strip().strip('"\'')
            return CommandType.UPLOAD_TEMPLATE, path, {}

        # 普通文本
        return CommandType.TEXT, text, {}

    def parse_mode(self, mode_input: str) -> Optional[TaskType]:
        """解析模式输入"""
        mode_lower = mode_input.lower().strip()
        return self.WORK_MODES.get(mode_lower)

    def get_menu_text(self) -> str:
        """获取菜单文本"""
        menu_lines = [
            "【工作模式】",
            "1. 对话模式 - 直接与AI交流",
            "2. 文档理解 - 理解并分析文档内容",
            "3. 文档编辑 - 编辑Word文档（也可用 agent_a）",
            "4. 实体提取 - 从文档提取结构化数据（需要模板）",
            "5. 表格填表 - 使用Excel数据填入模板（也可用 agent_d）",
            "",
            "【命令】",
            "• select <模式> - 选择工作模式",
            "• upload data <路径> - 上传原数据文件",
            "• upload template <路径> - 上传模板文件",
            "• status - 查看当前状态",
            "• reset - 重置会话",
            "• menu - 显示此菜单",
        ]
        return "\n".join(menu_lines)

    def get_status_text(self, session: SessionState) -> str:
        """获取状态文本"""
        lines = ["【当前状态】"]

        mode_name = self.MODE_DISPLAY_NAMES.get(session.task_type, "未知")
        lines.append(f"工作模式: {mode_name}")

        if session.data_files:
            lines.append(f"原数据: {len(session.data_files)} 个文件")
            for f in session.data_files:
                lines.append(f"  - {f.name}")
        else:
            lines.append("原数据: 未上传")

        if session.template_file:
            lines.append(f"模板: {session.template_file.name}")
        else:
            lines.append("模板: 未上传")

        return "\n".join(lines)


# 全局单例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

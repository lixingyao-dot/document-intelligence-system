"""
输入处理器
解析用户输入，生成任务规格对象
"""
from typing import List, Optional

from core.orchestrator.task_spec import (
    TaskSpec, TaskType, FileInfo,
    detect_task_type_from_files
)
from utils.logger import get_logger
from user_layer.file_upload import FileUploader
from user_layer.session_manager import (
    get_session_manager, CommandType, SessionState
)


class InputHandler:
    """
    输入处理器
    支持命令式交互，提取文件并维护会话状态
    """

    def __init__(self, session_id: str = "default"):
        self.logger = get_logger(__name__)
        self.file_uploader = FileUploader()
        self.session_manager = get_session_manager()
        self.session_id = session_id

    def parse(self, user_input: str) -> tuple[TaskSpec, Optional[str]]:
        """
        解析用户输入
        返回: (任务规格, 系统响应消息) 消息为None表示正常处理
        """
        session = self.session_manager.get_session(self.session_id)
        command_type, clean_text, extra = self.session_manager.parse_command(user_input)

        # 处理命令
        if command_type == CommandType.MENU:
            menu_text = self.session_manager.get_menu_text()
            return self._create_conversation_spec(session), menu_text

        if command_type == CommandType.SHOW_STATUS:
            status_text = self.session_manager.get_status_text(session)
            return self._create_conversation_spec(session), status_text

        if command_type == CommandType.RESET:
            self.session_manager.reset_session(self.session_id)
            return self._create_conversation_spec(session), "会话已重置"

        if command_type == CommandType.SELECT_MODE:
            new_mode = self.session_manager.parse_mode(clean_text)
            if new_mode:
                session.task_type = new_mode
                mode_name = self.session_manager.MODE_DISPLAY_NAMES.get(new_mode, "未知")
                return self._create_conversation_spec(session), f"已切换到: {mode_name}"
            return self._create_conversation_spec(session), "未知模式，请使用 menu 查看可用模式"

        if command_type == CommandType.UPLOAD_DATA:
            return self._upload_data(session, clean_text)

        if command_type == CommandType.UPLOAD_TEMPLATE:
            return self._upload_template(session, clean_text)

        # 普通文本 - 更新指令并创建任务规格
        session.custom_instruction = clean_text
        task_spec = self._create_task_spec(session)
        return task_spec, None

    def _upload_data(self, session: SessionState, path: str) -> tuple[TaskSpec, Optional[str]]:
        """上传原数据"""
        if not path:
            return self._create_conversation_spec(session), "请提供文件路径"

        result = self.file_uploader.upload(path)
        if result.success and result.file_info:
            session.data_files.append(result.file_info)
            return self._create_task_spec(session), f"已上传原数据: {result.file_info.name}"
        return self._create_conversation_spec(session), f"上传失败: {result.error}"

    def _upload_template(self, session: SessionState, path: str) -> tuple[TaskSpec, Optional[str]]:
        """上传模板"""
        if not path:
            return self._create_conversation_spec(session), "请提供文件路径"

        result = self.file_uploader.upload(path)
        if result.success and result.file_info:
            session.template_file = result.file_info
            return self._create_task_spec(session), f"已上传模板: {result.file_info.name}"
        return self._create_conversation_spec(session), f"上传失败: {result.error}"

    def _create_conversation_spec(self, session: SessionState) -> TaskSpec:
        """创建对话模式任务规格"""
        return TaskSpec(
            task_type=TaskType.DEFAULT_CONVERSATION,
            instruction="",
            source_files=[],
        )

    def _create_task_spec(self, session: SessionState) -> TaskSpec:
        """根据会话状态创建任务规格"""
        # 优先使用用户选择的模式
        task_type = session.task_type

        # 如果没有选择特定模式，根据文件自动检测
        if task_type == TaskType.DEFAULT_CONVERSATION and (session.data_files or session.template_file):
            all_files = session.data_files.copy()
            if session.template_file:
                all_files.append(session.template_file)
            task_type = detect_task_type_from_files(all_files)

        return TaskSpec(
            task_type=task_type,
            instruction=session.custom_instruction,
            source_files=session.data_files,
            template_file=session.template_file,
        )

    def get_current_state(self) -> dict:
        """获取当前会话状态摘要"""
        session = self.session_manager.get_session(self.session_id)
        return {
            "task_type": session.task_type.value,
            "data_files_count": len(session.data_files),
            "has_template": session.template_file is not None,
            "has_instruction": bool(session.custom_instruction),
        }

"""
CLI交互界面
命令行用户交互界面
"""
import re
from typing import Optional, List, Tuple
import sys
import os
from pathlib import Path

from config import SystemConfig
from core.orchestrator import WorkflowCoordinator, TaskSpec, TaskType, FileInfo
from core.orchestrator.task_spec import detect_task_type_from_files
from utils.logger import get_logger
from user_layer.file_upload import FileUploader
from user_layer.input_handler import InputHandler
from user_layer.system_guide import get_system_guide


def strip_markdown(text: str) -> str:
    """移除文本中的markdown格式符号"""
    # 移除粗体、斜体等
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)      # __bold__
    text = re.sub(r'_(.+?)_', r'\1', text)        # _italic_
    # 移除行内代码
    text = re.sub(r'`(.+?)`', r'\1', text)        # `code`
    # 移除列表标记 - 在行首的 -, *, 数字.
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)  # - item
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)  # 1. item
    # 移除标题标记 #
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)      # # heading
    # 移除常见emoji
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)
    text = re.sub(r'[\U00002600-\U000027BF]', '', text)
    # 移除每行行首空白
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    text = '\n'.join(lines)
    # 清理多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class CLIInterface:
    """
    CLI交互界面
    处理用户输入、任务选择和结果显示
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or SystemConfig()
        self.logger = get_logger(__name__)
        self.coordinator = WorkflowCoordinator(self.config)
        self.file_uploader = FileUploader(self.config)
        self.input_handler = InputHandler()
        self.conversation_history: List[dict] = []
        self.current_task_type: Optional[TaskType] = None
        self.uploaded_files: List[FileInfo] = []  # 已上传的文件池
        self.selected_files: List[FileInfo] = []  # 选中的文件（实际传给 Agent）
        self.template_file: Optional[FileInfo] = None

        # 保存 DocumentAgent 实例供交互式对话使用
        self._document_agent_instance = None

    def run(self):
        """
        启动CLI界面
        统一的交互循环，所有模式都在这里处理
        """
        self._print_welcome()

        while True:
            try:
                user_input = input("\n[用户]: ").strip()

                if not user_input:
                    continue

                # 检查退出命令
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("\n感谢使用文档智能系统，再见！")
                    break

                # 处理系统命令（这些命令在所有模式下都可使用）
                if self._handle_system_command(user_input):
                    continue

                # === 统一的消息处理 ===
                # 根据当前模式决定响应来源
                if self.current_task_type == TaskType.DOCUMENT_UNDERSTANDING:
                    # 文档理解模式 - 允许无文件进入，但对话时需要选中文件
                    if self._document_agent_instance is None:
                        self._init_document_agent()

                    # 调用 DocumentAgent（可能还没有初始化或没有选中文件）
                    print("\n[DocumentAgent 思考中...]")
                    response = self._document_agent_instance.chat(user_input)
                    print(f"\n[DocumentAgent]: {response}\n")

                elif self.current_task_type == TaskType.DOCUMENT_EDITING:
                    # 文档编辑模式
                    if not self.selected_files:
                        print("\n请先选择文档文件!")
                        print("  upload data <路径>    - 上传文件")
                        print("  select data [编号]    - 选择文件")
                        continue
                    response = self._process_input(user_input)
                    if response.strip():
                        print(f"\n[系统]: {strip_markdown(response)}")

                elif self.current_task_type == TaskType.ENTITY_EXTRACTION:
                    # 实体提取模式
                    if not self.selected_files:
                        print("\n请先选择文档文件!")
                        continue
                    response = self._process_input(user_input)
                    if response.strip():
                        print(f"\n[系统]: {strip_markdown(response)}")

                elif self.current_task_type == TaskType.TABLE_FILLING:
                    # 表格填表模式
                    if not self.selected_files:
                        print("\n请先选择数据文件!")
                        continue
                    response = self._process_input(user_input)
                    if response.strip():
                        print(f"\n[系统]: {strip_markdown(response)}")

                else:
                    # 默认对话模式
                    response = self._process_input(user_input)
                    if not self.config.llm.streaming:
                        print(f"\n[系统]: {strip_markdown(response)}")

            except KeyboardInterrupt:
                print("\n\n已退出系统。")
                break
            except Exception as e:
                self.logger.error(f"处理输入时出错: {str(e)}")
                print(f"\n[错误]: {str(e)}")

    def _init_document_agent(self):
        """初始化 DocumentAgent（静默模式，不重复打印）"""
        if self._document_agent_instance is not None:
            # 已初始化，更新选中的文档即可
            if self.selected_files:
                self._document_agent_instance.set_documents(self.selected_files)
            return

        task_spec = TaskSpec(
            task_type=TaskType.DOCUMENT_UNDERSTANDING,
            source_files=self.selected_files
        )

        result = self.coordinator.execute(task_spec)

        if not result.success or not result.interactive_agent:
            print(f"\n无法启动 DocumentAgent: {result.message}")
            self._document_agent_instance = None
            return

        self._document_agent_instance = result.interactive_agent

        # 只在第一次初始化时打印
        print(f"\n[OK] DocumentAgent 已就绪")
        if self.selected_files:
            print(f"  已选中文档 ({len(self.selected_files)} 个):")
            for f in self.selected_files:
                print(f"    - {f.name}")
        else:
            print("  当前无选中文档")
            print("  请先上传并选择文档:")
            print("    upload data <路径>")
            print("    select data [编号]")
        print()

    def _print_welcome(self):
        """打印欢迎信息"""
        guide = get_system_guide()
        print("\n" + "=" * 60)
        print("欢迎使用文档智能系统")
        print("=" * 60)
        print(guide)
        print("\n" + "-" * 60)
        self._print_context_help()

    def _print_context_help(self):
        """打印当前上下文下的帮助信息"""
        mode = self._get_current_mode_name()
        print(f"\n[当前模式: {mode}]")
        print("-" * 60)
        print("通用命令:")
        print("  upload data <路径>      - 上传数据文件")
        print("  upload template <路径>   - 上传模板文件")
        print("  select data [编号]      - 选择数据文件")
        print("  select template [编号]   - 选择模板文件")
        print("  files                  - 查看已上传文件")
        print("  menu                   - 切换工作模式")
        print("  help                   - 显示帮助")
        print("  exit                   - 退出系统")

        # 根据当前模式显示特定命令
        if self.current_task_type == TaskType.DOCUMENT_UNDERSTANDING:
            print("\n文档理解命令:")
            print("  /add <路径>    - 添加新文档到当前会话")
            print("  /clear        - 清除对话历史")
            print("  /history      - 查看对话历史")
            print("  /doc          - 显示当前文档列表")
            print("  /mode         - 显示当前模式信息")

        print("-" * 60)

    def _get_current_mode_name(self) -> str:
        """获取当前模式名称"""
        mode_map = {
            TaskType.DEFAULT_CONVERSATION: "默认对话",
            TaskType.DOCUMENT_UNDERSTANDING: "文档理解",
            TaskType.DOCUMENT_EDITING: "文档编辑",
            TaskType.ENTITY_EXTRACTION: "实体提取",
            TaskType.TABLE_FILLING: "表格填表",
        }
        return mode_map.get(self.current_task_type, "默认对话")

    def _show_current_mode(self):
        """显示当前模式信息"""
        mode = self._get_current_mode_name()
        print(f"\n[当前模式: {mode}]")
        if self.selected_files:
            print(f"[已选中文档: {len(self.selected_files)} 个文件]")
        elif self.uploaded_files:
            print(f"[已上传: {len(self.uploaded_files)} 个文件，可用 select data 选择]")

    def _handle_system_command(self, user_input: str) -> bool:
        """处理系统命令"""
        cmd = user_input.lower().strip()

        # === 文档理解模式专用命令 ===
        if self.current_task_type == TaskType.DOCUMENT_UNDERSTANDING:
            if user_input.lower() == "/clear":
                if self._document_agent_instance:
                    self._document_agent_instance.clear_history()
                    print("  [已清除对话历史]")
                return True

            if user_input.lower() == "/history":
                if self._document_agent_instance:
                    history = self._document_agent_instance.get_history()
                    print(f"\n  [对话历史: {len(history)} 条消息]")
                    for i, msg in enumerate(history):
                        role = "你" if msg["role"] == "user" else "Agent"
                        content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                        print(f"  {i+1}. [{role}] {content}")
                    print()
                return True

            if user_input.lower() == "/files":
                self._show_uploaded_files()
                return True

            if user_input.lower().startswith("/add "):
                file_path = user_input[5:].strip().strip('<>').strip()
                if file_path:
                    self._upload_source_file(file_path)
                    # 更新 DocumentAgent 的文档
                    if self._document_agent_instance and self.selected_files:
                        self._document_agent_instance.set_documents(self.selected_files)
                    elif self._document_agent_instance and self.uploaded_files:
                        print("  提示: 请先用 'select data [编号]' 选择文件")
                else:
                    print("  请提供文件路径: /add <路径>")
                return True

            if user_input.lower() == "/mode":
                self._show_current_mode()
                return True

            if user_input.lower() == "/doc":
                # 显示当前文档信息
                if self.selected_files:
                    print(f"\n  [已选中文档 ({len(self.selected_files)} 个)]:")
                    for f in self.selected_files:
                        print(f"    - {f.name}")
                elif self.uploaded_files:
                    print(f"\n  [已上传 ({len(self.uploaded_files)} 个)，未选择]:")
                    for i, f in enumerate(self.uploaded_files, 1):
                        print(f"    {i}. {f.name}")
                    print("\n  使用 'select data [编号]' 选择文件")
                else:
                    print("\n  [当前无文档]")
                return True

        # === 通用命令 ===
        if cmd in ["help", "h", "帮助"]:
            self._print_context_help()
            return True

        if cmd in ["menu", "m", "菜单"]:
            self._print_workflow_menu()
            return True

        # 文件上传命令
        if self._handle_upload_command(user_input):
            return True

        # 文件选择命令 - 必须在工作流选择之前检查
        if cmd.startswith("select data"):
            # 提取编号或名称部分
            selection = cmd[11:].strip() if cmd.startswith("select data ") else ""  # 跳过 "select data"
            selection = selection.lstrip()  # 移除多余空格
            if selection:
                self._select_data_file(selection)
            else:
                self._show_data_files()
            return True

        if cmd.startswith("select template"):
            selection = cmd[14:].strip() if cmd.startswith("select template ") else ""  # 跳过 "select template"
            selection = selection.lstrip()
            if selection:
                self._select_template_file(selection)
            else:
                self._show_template_files()
            return True

        # 工作流选择命令 - 放在文件选择之后
        if cmd.startswith("select ") or cmd.startswith("选择 "):
            mode = cmd.split(" ", 1)[1] if " " in cmd else ""
            self._select_workflow_mode(mode)
            return True

        # 显示已上传文件
        if cmd in ["files", "list", "ls", "文件", "已上传"]:
            self._show_uploaded_files()
            return True

        # 清除文件
        if cmd in ["clear", "clear files", "清除"]:
            self._clear_uploaded_files()
            return True

        return False

    def _handle_upload_command(self, user_input: str) -> bool:
        """处理文件上传命令"""
        cmd = user_input.lower().strip()

        # upload <路径> 简短命令（上传原数据）
        if cmd.startswith("upload ") and not cmd.startswith("upload data ") and not cmd.startswith("upload template ") and not cmd.startswith("上传"):
            file_path = user_input[7:].strip().strip('<>').strip()
            if file_path:
                self._upload_source_file(file_path)
            else:
                print("\n请提供文件路径，例如: upload C:\\path\\to\\file.docx")
            return True

        # upload data <路径> 命令 - 用split跳过前两个词
        if cmd.startswith("upload data ") or cmd.startswith("上传原数据 ") or cmd.startswith("上传数据 "):
            parts = user_input.split(" ", 2)  # 分成最多3部分
            file_path = parts[2] if len(parts) > 2 else ""
            file_path = file_path.strip().strip('<>').strip()
            if file_path:
                self._upload_source_file(file_path)
            else:
                print("\n请提供文件路径，例如: upload data C:\\path\\to\\file.docx")
            return True

        if cmd in ["upload data", "上传原数据", "上传数据", "data"]:
            print("\n请提供文件路径，例如: upload data C:\\path\\to\\file.docx")
            print("支持的原数据类型: docx, pdf, txt, md, xlsx, xls, csv")
            return True

        # upload template <路径> 命令
        if cmd.startswith("upload template ") or cmd.startswith("上传模板 "):
            parts = user_input.split(" ", 2)
            file_path = parts[2] if len(parts) > 2 else ""
            file_path = file_path.strip().strip('<>').strip()
            if file_path:
                self._upload_template_file(file_path)
            else:
                print("\n请提供文件路径，例如: upload template C:\\path\\to\\template.xlsx")
            return True

        if cmd in ["upload template", "上传模板", "template"]:
            print("\n请提供文件路径，例如: upload template C:\\path\\to\\template.xlsx")
            print("支持的模板类型: xlsx, xls, docx")
            return True

        return False

    def _upload_source_file(self, file_path: str):
        """上传原数据文件"""
        # 处理相对路径
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        result = self.file_uploader.upload(file_path)
        if result.success:
            # 添加到已上传文件池
            self.uploaded_files.append(result.file_info)
            print(f"\n[OK] 原数据上传成功!")
            print(f"  文件名: {result.file_info.name}")
            print(f"  类型: {result.file_info.file_type.value}")
            print(f"  大小: {result.file_info.size / 1024:.2f} KB")
            print(f"  当前已上传 {len(self.uploaded_files)} 个文件")
            print(f"\n  使用 'select data [编号]' 选择文件给 Agent 使用")
        else:
            print(f"\n[ERR] 上传失败: {result.message}")

    def _upload_template_file(self, file_path: str):
        """上传模板文件"""
        # 处理相对路径
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        result = self.file_uploader.upload(file_path)
        if result.success:
            self.template_file = result.file_info
            print(f"\n[OK] 模板上传成功!")
            print(f"  文件名: {result.file_info.name}")
            print(f"  类型: {result.file_info.file_type.value}")
            print(f"  大小: {result.file_info.size / 1024:.2f} KB")
        else:
            print(f"\n[ERR] 上传失败: {result.message}")

    def _add_source_file(self, file_path: str):
        """添加额外的源文件"""
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        # 检查文件是否已存在
        for existing in self.uploaded_files:
            if existing.path == file_path:
                print(f"\n文件已在上传列表中: {existing.name}")
                return

        result = self.file_uploader.upload(file_path)
        if result.success:
            self.uploaded_files.append(result.file_info)
            print(f"\n[OK] 已添加文件: {result.file_info.name}")
            print(f"  当前已上传 {len(self.uploaded_files)} 个文件")
            print(f"  使用 'select data [编号]' 选择文件")
        else:
            print(f"\n[ERR] 添加失败: {result.message}")

    def _show_uploaded_files(self):
        """显示已上传的文件"""
        print("\n" + "-" * 40)
        print("已上传文件:")
        print("-" * 40)

        if self.uploaded_files:
            print(f"上传列表 ({len(self.uploaded_files)} 个):")
            for i, f in enumerate(self.uploaded_files, 1):
                selected_mark = " [OK]" if f in self.selected_files else ""
                print(f"  {i}. {f.name} [{f.file_type.value}]{selected_mark}")
        else:
            print("原数据: (未上传)")

        if self.selected_files:
            print(f"\n已选中文档 ({len(self.selected_files)} 个):")
            for f in self.selected_files:
                print(f"  - {f.name}")

        if self.template_file:
            print(f"\n模板: {self.template_file.name} [{self.template_file.file_type.value}]")

        if self.current_task_type:
            print(f"\n当前模式: {self.current_task_type.value}")

        print("-" * 40)

    def _clear_uploaded_files(self):
        """清除已上传的文件"""
        self.uploaded_files = []
        self.selected_files = []
        self.template_file = None
        self._document_agent_instance = None  # 清除 Agent 实例
        self.file_uploader.clear_uploaded_files()
        print("\n已清除所有已上传的文件。")

    def _show_data_files(self):
        """显示可选择的数据文件列表"""
        print("\n" + "-" * 50)
        print("已上传的数据文件:")
        print("-" * 50)

        if not self.uploaded_files:
            print("  (无已上传文件)")
        else:
            for i, f in enumerate(self.uploaded_files, 1):
                selected_mark = " [OK]" if f in self.selected_files else ""
                print(f"  {i}. {f.name} [{f.file_type.value}]{selected_mark}")
                print(f"     {f.path}")

        print("-" * 50)
        if self.selected_files:
            print(f"\n已选择 {len(self.selected_files)} 个文件给 Agent")
        else:
            print("\n使用方法:")
            print("  select data <编号>  - 选择数据文件")

    def _select_data_file(self, selection: str):
        """选择数据文件"""
        if not self.uploaded_files:
            print("\n没有已上传的文件，请先上传文件:")
            print("  upload data <路径>")
            return

        try:
            index = int(selection) - 1
            if 0 <= index < len(self.uploaded_files):
                selected = self.uploaded_files[index]
                # 添加到选中列表
                if selected not in self.selected_files:
                    self.selected_files.append(selected)
                print(f"\n[OK] 已选择: {selected.name}")
                # 如果在文档理解模式，更新 Agent
                if self.current_task_type == TaskType.DOCUMENT_UNDERSTANDING and self._document_agent_instance:
                    self._document_agent_instance.set_documents(self.selected_files)
                    print(f"  DocumentAgent 已更新，当前有 {len(self.selected_files)} 个选中文档")
            else:
                print(f"\n编号无效，范围: 1-{len(self.uploaded_files)}")
        except ValueError:
            # 按名称匹配
            matching = [f for f in self.uploaded_files if selection.lower() in f.name.lower()]
            if matching:
                print(f"\n匹配到 {len(matching)} 个文件:")
                for i, f in enumerate(matching, 1):
                    selected_mark = " (已选)" if f in self.selected_files else ""
                    print(f"  {self.uploaded_files.index(f) + 1}. {f.name}{selected_mark}")
                print(f"\n输入编号选择: select data [编号]")
            else:
                print(f"\n未找到匹配 '{selection}' 的文件")

    def _show_template_files(self):
        """显示可选择的模板文件"""
        print("\n" + "-" * 50)
        print("已上传的模板文件:")
        print("-" * 50)

        if not self.template_file:
            print("  (无已上传模板)")
        else:
            print(f"  1. {self.template_file.name} [{self.template_file.file_type.value}]")
            print(f"     {self.template_file.path}")

        print("-" * 50)

    def _select_template_file(self, selection: str):
        """选择模板文件"""
        if not self.template_file:
            print("\n没有已上传的模板文件，请先上传模板。")
            print("  upload template <路径>")
            return

        print(f"\n[OK] 已选择模板文件: {self.template_file.name}")
        print(f"  路径: {self.template_file.path}")

    def _get_mode_requirements(self, task_type: TaskType) -> str:
        """获取模式所需的文件"""
        requirements = {
            TaskType.DOCUMENT_UNDERSTANDING: "可选: 原数据文件 (docx/pdf/txt/md)，可先进入再上传",
            TaskType.DOCUMENT_EDITING: "需要: 原数据文件 (docx)",
            TaskType.ENTITY_EXTRACTION: "需要: 原数据文件 (docx/pdf/txt/md) + 模板文件 (xlsx)",
            TaskType.TABLE_FILLING: "需要: 原数据文件 (xlsx) + 模板文件 (xlsx/docx)",
            TaskType.DEFAULT_CONVERSATION: "无需特定文件，可直接对话",
        }
        return requirements.get(task_type, "未知要求")

    def _print_workflow_menu(self):
        """打印工作流菜单"""
        print("\n" + "-" * 50)
        print("可选的工作模式:")
        workflows = self.coordinator.get_available_workflows()
        for key, desc in workflows.items():
            print(f"  {key}: {desc}")

        print("\n各模式文件要求:")
        print("  1. 默认对话模式 - 无需文件，直接对话")
        print("  2. 文档理解模式 - 需要原数据(docx/pdf/txt/md)")
        print("  3. 文档编辑模式 - 需要原数据(docx)")
        print("  4. 实体提取模式 - 需要原数据 + 模板(xlsx)")
        print("  5. 表格填表模式 - 需要原数据(xlsx) + 模板(xlsx/docx)")
        print("-" * 50)

        print("\n使用方式:")
        print("  1. 选择模式: select <模式名或数字>")
        print("  2. 文档编辑: select agent_a")
        print("  3. 表格填表: select agent_d")
        print("  4. 上传原数据: upload data <文件路径>")
        print("  5. 上传模板: upload template <文件路径>")
        print("  6. 执行任务: 输入您的需求或任务描述")

    def _select_workflow_mode(self, mode: str):
        """选择工作模式"""
        mode_map = {
            "1": TaskType.DEFAULT_CONVERSATION,
            "2": TaskType.DOCUMENT_UNDERSTANDING,
            "3": TaskType.DOCUMENT_EDITING,
            "4": TaskType.ENTITY_EXTRACTION,
            "5": TaskType.TABLE_FILLING,
            "default": TaskType.DEFAULT_CONVERSATION,
            "document_understanding": TaskType.DOCUMENT_UNDERSTANDING,
            "document_editing": TaskType.DOCUMENT_EDITING,
            "agent_a": TaskType.DOCUMENT_EDITING,
            "agent a": TaskType.DOCUMENT_EDITING,
            "entity_extraction": TaskType.ENTITY_EXTRACTION,
            "table_filling": TaskType.TABLE_FILLING,
            "agent_d": TaskType.TABLE_FILLING,
            "agent d": TaskType.TABLE_FILLING,
        }

        task_type = mode_map.get(mode.lower())
        if task_type:
            self.current_task_type = task_type
            # 同步到 InputHandler 会话状态，避免后续解析回落到默认对话
            session_state = self.input_handler.session_manager.get_session(self.input_handler.session_id)
            session_state.task_type = task_type
            print(f"\n已选择模式: {task_type.value}")
            print(f"  {self._get_mode_requirements(task_type)}")

            # 如果已上传文件，检查是否满足要求
            self._check_file_requirements(task_type)

            # 文档理解模式：初始化 Agent
            if task_type == TaskType.DOCUMENT_UNDERSTANDING:
                print("\n已就绪！现在可以:")
                if self.selected_files:
                    print(f"  [OK] 已选中文档 {len(self.selected_files)} 个，可直接对话")
                elif self.uploaded_files:
                    print(f"  已上传 {len(self.uploaded_files)} 个文件")
                    print("  使用 'select data [编号]' 选择文件")
                else:
                    print("  上传文档: upload data <路径>")
                print("  输入 /help 查看命令\n")
        else:
            print("\n未知模式，请使用菜单中的选项。")

    def _check_file_requirements(self, task_type: TaskType):
        """检查文件是否满足当前模式要求"""
        issues = []

        # 文档理解模式不需要文件，可直接进入
        if task_type == TaskType.DOCUMENT_UNDERSTANDING:
            if self.selected_files:
                print(f"  [OK] 已选中文档 {len(self.selected_files)} 个")
            elif self.uploaded_files:
                print(f"  已上传 {len(self.uploaded_files)} 个，请先 select")
                print("  upload data → select data → 对话")
            else:
                print("  提示: 可以先上传文档，或者直接对话")
            return

        # 检查是否需要原数据
        if task_type in [TaskType.DOCUMENT_EDITING,
                         TaskType.ENTITY_EXTRACTION, TaskType.TABLE_FILLING]:
            if not self.selected_files:
                issues.append("原数据文件未选择")

        # 检查是否需要模板
        if task_type in [TaskType.ENTITY_EXTRACTION, TaskType.TABLE_FILLING]:
            if not self.template_file:
                issues.append("模板文件未上传")

        if issues:
            print("\n[WARN] 文件要求:")
            for issue in issues:
                print(f"  - {issue}")
            print("\n请使用以下命令:")
            print("  upload data <路径>     - 上传文件")
            print("  select data [编号]      - 选择文件")
        else:
            print("\n[OK] 文件已准备就绪，可以开始执行任务")

    def _validate_mode_files(self, task_type: TaskType) -> Tuple[bool, str]:
        """验证当前模式的文件是否满足要求"""
        if task_type == TaskType.DEFAULT_CONVERSATION:
            return True, "默认对话模式无需文件"

        # 文档理解模式：不需要选中文件
        if task_type == TaskType.DOCUMENT_UNDERSTANDING:
            return True, "文档理解模式"

        # 检查原数据（需要选中）
        if task_type in [TaskType.DOCUMENT_EDITING,
                         TaskType.ENTITY_EXTRACTION, TaskType.TABLE_FILLING]:
            if not self.selected_files:
                return False, "请先选择原数据文件"

            # 检查文件类型
            selected_type = self.selected_files[0].file_type.value.lower()
            allowed_types = {
                TaskType.DOCUMENT_EDITING: ["DOCX", "docx"],
                TaskType.ENTITY_EXTRACTION: ["DOCX", "docx", "PDF", "pdf", "TXT", "txt", "MD", "md"],
                TaskType.TABLE_FILLING: ["XLSX", "xlsx", "XLS", "xls"],
            }
            if selected_type not in allowed_types.get(task_type, []):
                return False, f"该模式不支持 {selected_type} 格式"

        # 检查模板
        if task_type in [TaskType.ENTITY_EXTRACTION, TaskType.TABLE_FILLING]:
            if not self.template_file:
                return False, "请先上传模板文件"

            template_type = self.template_file.file_type.value.lower()
            template_types = {
                TaskType.ENTITY_EXTRACTION: ["XLSX", "xlsx", "XLS", "xls"],
                TaskType.TABLE_FILLING: ["XLSX", "xlsx", "XLS", "xls", "DOCX", "docx"],
            }
            if template_type not in template_types.get(task_type, []):
                return False, f"该模式不支持 {template_type} 格式的模板"

        return True, "文件验证通过"

    def _apply_default_output_paths(self, task_spec: TaskSpec, task_type: TaskType, source_files: List[FileInfo]):
        """为 CLI 执行补齐默认输出路径，保存在源文件同目录。"""
        if task_spec.output_file or not source_files:
            return

        source_path = Path(source_files[0].path).resolve()
        base_dir = source_path.parent
        stem = source_path.stem

        if task_type == TaskType.DOCUMENT_EDITING:
            task_spec.output_file = str(base_dir / f"{stem}_edited{source_path.suffix}")
            return

        if task_type == TaskType.ENTITY_EXTRACTION:
            task_spec.output_file = str(base_dir / f"{stem}_extracted.json")
            task_spec.parameters["allow_rule_fallback"] = True
            if task_spec.template_file:
                template_suffix = Path(task_spec.template_file.path).suffix.lower() or ".xlsx"
                task_spec.parameters.setdefault(
                    "template_output_file",
                    str(base_dir / f"{stem}_filled{template_suffix}"),
                )
            return

        if task_type == TaskType.TABLE_FILLING:
            task_spec.output_file = str(base_dir / f"{stem}_filtered.json")
            task_spec.parameters["allow_rule_fallback"] = True
            if task_spec.template_file:
                template_suffix = Path(task_spec.template_file.path).suffix.lower() or ".xlsx"
                task_spec.parameters.setdefault(
                    "template_output_file",
                    str(base_dir / f"{stem}_filled{template_suffix}"),
                )

    def _process_input(self, user_input: str) -> str:
        """
        处理用户输入
        根据输入内容决定是进入对话模式还是执行任务
        """
        # 解析用户输入
        task_spec, system_msg = self.input_handler.parse(user_input)

        # 如果有系统消息（命令响应），先显示
        if system_msg:
            print(f"\n[系统]: {system_msg}")

        # 命令响应后，等待用户下一步输入
        if task_spec.task_type == TaskType.DEFAULT_CONVERSATION and not task_spec.instruction:
            return ""

        # 更新当前文件状态（从会话中同步）
        session_state = self.input_handler.session_manager.get_session(self.input_handler.session_id)
        if session_state.data_files:
            self.uploaded_files = session_state.data_files

        # 确定任务类型：优先使用 CLI 显式选择的模式
        if self.current_task_type is not None:
            task_type = self.current_task_type
        else:
            # 未显式选模式时，基于当前选中文件自动检测
            all_files = self.selected_files.copy()
            if self.template_file:
                all_files.append(self.template_file)
            task_type = detect_task_type_from_files(all_files) if all_files else task_spec.task_type

        # 验证文件是否满足要求
        valid, msg = self._validate_mode_files(task_type)
        if not valid:
            return f"[WARN] {msg}\n\n请先上传并选择所需文件。"
        if task_type == TaskType.DOCUMENT_UNDERSTANDING:
            # 文档理解模式：使用选中的文件或空列表
            source_to_use = self.selected_files
        else:
            # 其他模式：使用选中的文件
            source_to_use = self.selected_files

        # 创建任务规格
        final_spec = TaskSpec(
            task_type=task_type,
            instruction=task_spec.instruction,
            source_files=source_to_use,
            template_file=self.template_file,
            parameters=dict(task_spec.parameters or {}),
            conversation_history=self.conversation_history
        )
        self._apply_default_output_paths(final_spec, task_type, source_to_use)

        # 添加到对话历史
        self.conversation_history.append({"role": "user", "content": user_input})

        # 执行工作流
        result = self.coordinator.execute(final_spec)

        # 添加到对话历史
        if result.data:
            response_message = result.data.message if hasattr(result.data, 'message') else str(result.data)
            self.conversation_history.append({
                "role": "assistant",
                "content": response_message
            })
            return response_message

        if result.success:
            return result.message
        else:
            return f"执行失败: {result.message}"

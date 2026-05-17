"""
DocumentAgent - 文档理解 Agent
支持交互式对话和多文件处理
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Generator, List, Optional, Any

from .base_agent import BaseAgent, AgentResponse
from config import SystemConfig, get_config
from core.orchestrator.task_spec import TaskSpec, FileInfo
from core.llm.llm_service import LLMService, get_llm_service
from utils.document_reader import read_document


# 默认文档理解系统提示词
DEFAULT_DOC_SYSTEM_PROMPT = """【身份】你是文档智能系统的 AI 助手，运行在【文档理解模式】下。

【核心能力】
1. **文档阅读** - 支持解析 docx、pdf、txt、md、xlsx、xls 等多种格式文档
2. **内容理解** - 准确理解文档结构、文字、数据和图表
3. **智能问答** - 围绕已上传的文档内容回答用户问题，支持多轮追问
4. **统计分析** - 对表格数据进行统计（均值、中位数、标准差、分位数等）
5. **要点提炼** - 提取文档核心观点、关键信息和数据结构

【工作原则】
- 始终基于已上传的文档内容回答，不要编造未提及的信息
- 回答应简洁准确，优先使用 Markdown 格式（列表、粗体等）
- 如果用户的问题涉及文档中未包含的内容，明确告知
- 当文档包含表格数据时，先给出统计概览，再按需展开细节
- 多文档场景下，区分说明各文档的内容和回答依据

【系统说明】
- 你只能访问用户通过界面上传的文档
- 文件路径和上传信息仅供参考，请勿在回答中暴露文件物理路径"""


class DocumentAgent(BaseAgent):
    """
    文档理解 Agent
    支持：
    - 交互式多轮对话
    - 多文件处理
    - 自动从用户指令或预设文件中获取文档
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        super().__init__(config)
        self.name = "DocumentAgent"
        self.agent_type = "document_understanding"
        self._llm_service: LLMService = get_llm_service()
        self._messages_history: List[Dict[str, str]] = []
        self._source_files: List[FileInfo] = []
        self._document_contents: Dict[str, str] = {}  # path -> content

        # 优先用 config 中配置的 prompt，其次用默认提示词
        try:
            cfg = config or get_config()
            self._system_prompt = cfg.agent.get_prompt("document_understanding") or DEFAULT_DOC_SYSTEM_PROMPT
        except Exception:
            self._system_prompt = DEFAULT_DOC_SYSTEM_PROMPT

    def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
        """
        执行文档理解任务
        """
        is_valid, error_msg = self.validate_input(task_spec)
        if not is_valid:
            return AgentResponse(success=False, message=error_msg)

        try:
            # 获取 max_rows 参数（如果有）
            max_rows = kwargs.get('max_rows', 100)

            # 设置源文件
            if task_spec.source_files:
                self._source_files = task_spec.source_files
                self._load_documents(max_rows=max_rows)

            # 处理指令
            instruction = task_spec.instruction or ""

            # 如果有指令，处理一次对话
            if instruction:
                response = self._process_query(instruction)
                return AgentResponse(
                    success=True,
                    message="文档理解完成",
                    data={"response": response}
                )

            # 无指令时返回就绪状态
            return AgentResponse(
                success=True,
                message="文档理解 Agent 已就绪",
                data={"status": "ready", "files": [f.name for f in self._source_files]}
            )

        except Exception as e:
            return AgentResponse(
                success=False,
                message=f"处理失败: {str(e)}"
            )

    def _read_one_document(self, file_info: FileInfo, max_rows: int) -> str:
        ext = Path(file_info.path).suffix.lower()
        if ext in [".xlsx", ".xls"]:
            return read_document(file_info.path, max_rows=max_rows)
        return read_document(file_info.path)

    def _load_documents(self, max_rows: int = 100):
        """加载所有文档内容（多文件时并发解析）。"""
        to_load = [f for f in self._source_files if f.path not in self._document_contents]
        if not to_load:
            return
        workers = max(1, getattr(self.config.processing, "document_load_max_workers", 4))
        if len(to_load) <= 1 or workers <= 1:
            for file_info in to_load:
                try:
                    self._document_contents[file_info.path] = self._read_one_document(
                        file_info, max_rows
                    )
                except Exception as e:
                    self._document_contents[file_info.path] = f"[错误] {str(e)}"
            return
        with ThreadPoolExecutor(max_workers=min(workers, len(to_load))) as pool:
            futures = {
                pool.submit(self._read_one_document, fi, max_rows): fi for fi in to_load
            }
            for fut in as_completed(futures):
                fi = futures[fut]
                try:
                    self._document_contents[fi.path] = fut.result()
                except Exception as e:
                    self._document_contents[fi.path] = f"[错误] {str(e)}"

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """验证输入"""
        # 文档理解模式可以没有文件（用户可能通过指令提供）
        return True, ""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._system_prompt

    def set_system_prompt(self, prompt: str):
        """外部注入系统提示词（供 API 层覆盖默认行为）"""
        self._system_prompt = prompt

    def _build_llm_messages(self, query: str) -> List[Dict[str, str]]:
        """构建发给 LLM 的消息列表。"""
        msgs = [{"role": "system", "content": self._system_prompt}]
        msgs.extend(self._messages_history)
        doc_context = self._build_doc_context()
        if doc_context:
            enhanced = (
                f"请分析以下文档内容并回答用户问题：\n\n{doc_context}\n\n---\n\n用户问题: {query}"
            )
            msgs.append({"role": "user", "content": enhanced})
        else:
            # 无文档时：添加强约束系统提示，防止 LLM 幻觉
            # 这是防止幻觉的核心屏障，必须足够清晰和强硬
            no_doc_system = """【无文档场景 - 强制约束】

## 当前状态
当前没有任何文档已上传到系统中。

## 绝对禁止的行为
1. 绝对不要编造、假设或基于训练数据生成任何文档内容
2. 绝对不要回复任何类似「已收到您的文档」「我现在开始分析」「根据文档...」的内容
3. 绝对不要创建虚假的文档摘要、数据、表格或分析结果
4. 禁止使用「根据您上传的文档」「从上文中可以看出」等暗示性表述

## 正确的回复方式
- 如果用户请求分析/阅读/查看文档：礼貌告知没有文档，请用户上传后再分析
- 如果用户问其他问题：正常对话即可
- 回复应该简洁、自然，像正常对话一样
## 你的身份
 你是文档智能系统的文档理解模式的助手，可以用户您阅读、理解和分析上传的文档内容。

"""
            msgs.append({"role": "system", "content": no_doc_system})
            msgs.append({"role": "user", "content": query})
        return msgs

    def stream_chat(self, user_input: str) -> Generator[str, None, None]:
        """
        同步生成器：直接遍历 client.stream()，每个 chunk yield LLM 分片。
        在 async context 中用 async for 包装时，外层用 asyncio.to_thread。
        """
        from langchain_openai import ChatOpenAI

        # 构建消息（无文档时会自动添加防幻觉约束）
        messages = self._build_llm_messages(user_input)
        lc_messages = self._llm_service._convert_messages(messages)

        client = ChatOpenAI(
            **self._llm_service._chat_openai_kwargs(streaming=True),
        )

        def _chunk_text(chunk) -> str:
            raw = getattr(chunk, "content", None) or ""
            if isinstance(raw, str):
                return raw
            if isinstance(raw, list):
                parts = []
                for block in raw:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return "".join(parts)
            return str(raw)

        for chunk in client.stream(lc_messages):
            text = _chunk_text(chunk)
            if text:
                yield text

        self._messages_history.append({"role": "user", "content": user_input})
        # 注意：流式无法在此获取完整回复内容，对话历史只记录用户消息
        # 多轮对话精度由 _build_llm_messages 中的 _messages_history 控制

    def chat(self, user_input: str) -> str:
        """
        交互式对话接口（一次性返回完整回复）
        """
        messages = self._build_llm_messages(user_input)
        try:
            response = self._llm_service.chat(
                messages=messages,
                strip_markdown_output=False,
            )
        except Exception as e:
            return f"[错误] LLM 调用失败: {str(e)}"

        self._messages_history.append({"role": "user", "content": user_input})
        self._messages_history.append({"role": "assistant", "content": response})
        return response

    def set_documents(self, files: List[FileInfo], max_rows: int = 100):
        """设置要处理的文档列表

        :param files: 文件信息列表
        :param max_rows: Excel 文件最大读取行数
        """
        self._source_files = files
        self._load_documents(max_rows=max_rows)

    def set_document(self, file_path: str, max_rows: int = 100):
        """设置单个文档（兼容旧接口）

        :param file_path: 文件路径
        :param max_rows: Excel 文件最大读取行数
        """
        from core.orchestrator.task_spec import FileType

        ext = Path(file_path).suffix.lower().lstrip('.')
        file_type = FileType(ext) if ext in [e.value for e in FileType] else FileType.TXT

        file_info = FileInfo(
            path=file_path,
            file_type=file_type,
            name=Path(file_path).name
        )
        self._source_files = [file_info]
        self._load_documents(max_rows=max_rows)

    def get_document_content(self, file_path: Optional[str] = None) -> Optional[str]:
        """获取文档内容"""
        if file_path:
            return self._document_contents.get(file_path)
        if self._source_files:
            return self._document_contents.get(self._source_files[0].path)
        return None

    def get_excel_statistics(self, file_path: Optional[str] = None, max_rows: int = 10000) -> Dict[str, Any]:
        """
        获取Excel文件的统计信息（不含原始数据）

        对于大文件，使用此方法可以避免超出LLM上下文限制

        :param file_path: Excel文件路径，如果为None则使用第一个源文件
        :param max_rows: 最大分析行数
        :return: 统计信息字典
        """
        from utils.document_reader import get_excel_statistics as get_stats

        target_path = file_path or (self._source_files[0].path if self._source_files else None)
        if not target_path:
            return {"error": "没有指定文件"}

        return get_stats(target_path, max_rows=max_rows)

    def get_all_documents_summary(self) -> str:
        """获取所有文档的摘要信息"""
        if not self._document_contents:
            return ""

        summary_parts = []
        for file_info in self._source_files:
            content = self._document_contents.get(file_info.path, "")
            summary_parts.append(f"## {file_info.name}\n\n{content[:10000]}")

        return "\n\n---\n\n".join(summary_parts)

    def _extract_file_paths_from_text(self, text: str) -> List[str]:
        """从文本中提取文件路径"""
        paths = []

        # 模式1: 带引号或书名号的完整路径
        patterns = [
            r'["""\']([A-Za-z]:\\[^\n"""\'*?:]+|[/\w]+/[^\n"""\'*?:]+)["""\']',
            r'文件[：:]\s*([^\n\s]+)',
            r'path[：:]\s*([^\n\s]+)',
            r'读取[：:]\s*([^\n\s]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                path = match.strip()
                if os.path.isfile(path):
                    paths.append(path)

        # 模式2: 常见文档扩展名
        common_exts = ['.pdf', '.docx', '.txt', '.md', '.xlsx', '.csv', '.pptx', '.html']
        words = text.replace('\\', '/').split()
        for word in reversed(words):
            for ext in common_exts:
                if word.endswith(ext) and len(word) > 5:
                    clean_path = word.strip('.,;:!?\'"')
                    if os.path.isfile(clean_path) and clean_path not in paths:
                        paths.append(clean_path)

        return paths

    def _build_doc_context(self, file_paths: List[str] = None) -> str:
        """构建文档上下文"""
        if not self._document_contents:
            return ""

        context_parts = []
        paths_to_use = file_paths or [f.path for f in self._source_files]

        for path in paths_to_use:
            if path in self._document_contents:
                file_info = next((f for f in self._source_files if f.path == path), None)
                file_name = file_info.name if file_info else Path(path).name
                content = self._document_contents[path]

                # 截断过长的内容
                max_chars = 15000
                if len(content) > max_chars:
                    content = content[:max_chars] + f"\n\n[文档已截断，完整文档共 {len(content)} 字符]"

                context_parts.append(f"文档 ({file_name}):\n{content}")

        return "\n\n---\n\n".join(context_parts)

    def _process_query(self, query: str) -> str:
        """处理用户查询"""
        # 构建消息（无文档时会自动添加防幻觉约束）
        messages = self._build_llm_messages(query)

        # 调用 LLM
        try:
            cfg = self.config or get_config()
            response = self._llm_service.chat(
                messages=messages,
                model=cfg.llm.model,
                temperature=0
            )
        except Exception as e:
            return f"[错误] LLM 调用失败: {str(e)}"

        # 保存对话历史
        self._messages_history.append({"role": "user", "content": query})
        self._messages_history.append({"role": "assistant", "content": response})

        return response

    def chat(self, user_input: str) -> str:
        """
        交互式对话接口（供 CLI 调用）
        """
        return self._process_query(user_input)

    def clear_history(self):
        """清除对话历史"""
        self._messages_history.clear()

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._messages_history.copy()

    def _clean_markdown(self, text: str) -> str:
        """清理 markdown 格式"""
        if '```' in text:
            cleaned = re.sub(r'```[\w]*\n', '', text, flags=re.DOTALL)
            cleaned = re.sub(r'```', '', cleaned, flags=re.DOTALL)
            cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
            return cleaned
        return text


# 独立的聊天入口（用于直接运行测试）
def create_document_agent(config: Optional[SystemConfig] = None) -> DocumentAgent:
    """创建文档 Agent 实例"""
    return DocumentAgent(config)

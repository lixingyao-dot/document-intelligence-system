"""Agent 服务层 - 封装现有 Agent 供 API 调用"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from config import SystemConfig, get_config
from core.llm import get_llm_service
from core.llm.llm_service import _normalize_ai_content
from core.storage import download_file_to_local
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import TaskSpec, TaskType, FileInfo, FileType
from db.session_repository import get_messages, get_session_files
from langchain_openai import ChatOpenAI
from utils.chat_mode import normalize_chat_mode
from utils.logger import get_logger
from utils.llm_debug import mask_secret

_log = get_logger(__name__)

# ============================================================================
# Session 级别的 Agent 实例缓存
# 设计原则：文件和对话历史都跟随消息，agent 被同一个 session 复用
# ============================================================================
_agent_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _get_cached_agent(session_id: str, config: SystemConfig) -> Any:
    """
    获取或创建 session 对应的 DocumentAgent 实例。
    该实例在同一 session 的多次对话中被复用，对话历史累积。
    """
    with _cache_lock:
        if session_id not in _agent_cache:
            from core.agents.document_understand_agent import DocumentAgent
            _agent_cache[session_id] = DocumentAgent(config)
        return _agent_cache[session_id]


def clear_session_agent(session_id: str):
    """清除 session 对应的 agent 实例（当需要重置时调用）"""
    with _cache_lock:
        if session_id in _agent_cache:
            del _agent_cache[session_id]


def _resolve_local_file_path(file_dict: Dict[str, Any], config: SystemConfig, session_id: str = None) -> str:
    """把 storage_key 解析为可被本地 Agent 读取的临时文件路径。"""
    library_doc_id = str(file_dict.get("library_doc_id") or file_dict.get("doc_id") or "").strip()
    if library_doc_id:
        from utils.library_paths import resolve_library_doc_path

        lib_path = resolve_library_doc_path(library_doc_id, config)
        if lib_path and Path(lib_path).exists():
            return lib_path

    storage_key = str(file_dict.get("storage_key") or "").strip()
    if not storage_key:
        return ""

    file_name = str(file_dict.get("file_name") or storage_key).strip() or storage_key
    cache_dir = Path(config.temp_dir) / "file_cache" / (session_id or "shared")
    cache_path = cache_dir / file_name
    if cache_path.exists():
        return str(cache_path)

    try:
        return str(download_file_to_local(storage_key, cache_path, config=config))
    except Exception:
        pass

    # 本地临时文件路径检查：先尝试直接路径，再尝试相对路径
    storage_path = Path(storage_key)
    if storage_path.is_absolute() and storage_path.exists():
        return str(storage_path)

    # 尝试相对于项目根目录的路径
    upload_dir = Path("workspace/uploads")
    relative_path = upload_dir / storage_key if not str(storage_key).startswith(str(upload_dir)) else storage_path
    if relative_path.exists():
        return str(relative_path)

    # 如果文件存在于缓存目录的子目录中
    if session_id:
        session_cache_dir = cache_dir.parent / session_id
        if session_cache_dir.exists():
            for f in session_cache_dir.rglob("*"):
                if f.is_file() and f.name == file_name:
                    return str(f)

    # 返回原始路径，让调用方处理错误
    return storage_key


def set_agent_files(agent: Any, files: List[Dict[str, Any]], config: SystemConfig, session_id: str = None):
    """
    将消息携带的文件设置到 agent。
    设计：每次消息的文件都追加/更新到 agent，不清除旧文件。
    这样用户可以问"基于刚才的文件"或"基于所有上传的文件"。
    
    重要：如果 files 为空列表（表示用户主动取消了所有文件勾选），
    则清除 agent 的文档内容，防止使用旧文档产生幻觉。
    """
    # ========== 核心修复：无文件时清除 agent 的文档内容 ==========
    if not files:
        agent._document_contents = {}
        agent._source_files = []
        return

    selected = [f for f in files if f.get("is_selected", True)]
    if not selected:
        agent._document_contents = {}
        agent._source_files = []
        return

    db_files_cache: Optional[List[Any]] = None

    def _resolve_one(f: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        nonlocal db_files_cache
        file_path = _resolve_local_file_path(f, config, session_id)
        if not file_path and session_id and f.get("file_id"):
            if db_files_cache is None:
                db_files_cache = get_session_files(session_id, config=config)
            for db_file in db_files_cache:
                if db_file.id == f.get("file_id"):
                    file_path = _resolve_local_file_path(
                        {
                            "storage_key": getattr(db_file, "storage_key", None),
                            "file_name": getattr(db_file, "file_name", ""),
                        },
                        config,
                        session_id,
                    )
                    break
        return f, file_path

    workers = max(1, getattr(config.processing, "file_download_max_workers", 4))
    resolved: List[Tuple[Dict[str, Any], str]] = []
    if len(selected) <= 1 or workers <= 1:
        resolved = [_resolve_one(f) for f in selected]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(selected))) as pool:
            resolved = list(pool.map(_resolve_one, selected))

    file_infos = [
        FileInfo(path=fp, file_type=_get_file_type(f.get("file_name", "")))
        for f, fp in resolved
        if fp
    ]

    if file_infos:
        agent.set_documents(file_infos, max_rows=100)


def _get_file_type(file_name: str) -> FileType:
    """根据文件名判断文件类型"""
    ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
    mapping = {
        'pdf': FileType.PDF,
        'doc': FileType.DOCX,
        'docx': FileType.DOCX,
        'xls': FileType.XLSX,
        'xlsx': FileType.XLSX,
        'txt': FileType.TXT,
        'md': FileType.MD,
    }
    return mapping.get(ext, FileType.TXT)


def get_selected_session_files_payload(
    session_id: str, config: SystemConfig
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    从会话存储读取已勾选的数据文件与模板，组装为 Agent 所需的字典列表。
    前端发消息时未带 file_path，须以库中勾选状态为准。
    """
    rows = get_session_files(session_id, config=config)
    data_files: List[Dict[str, Any]] = []
    template_files: List[Dict[str, Any]] = []
    for f in rows:
        if not getattr(f, "is_selected", False):
            continue
        entry = {
            "storage_key": getattr(f, "storage_key", None),
            "file_name": f.file_name,
            "is_selected": True,
        }
        if f.file_type == "data":
            data_files.append(entry)
        elif f.file_type == "template":
            template_files.append(entry)
    return data_files, template_files


class AgentService:
    """Agent 服务封装 - 接入现有 Agent"""

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.coordinator = WorkflowCoordinator(self.config)

    async def _stream_sync_generator(self, gen):
        """
        将同步生成器包装为异步生成器，逐项 yield。
        用于在异步上下文中使用 DocumentAgent 的 stream_chat()。
        关键：必须在后台线程中运行同步生成器，否则会阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        def get_next():
            try:
                return next(gen)
            except StopIteration:
                return None
        while True:
            item = await loop.run_in_executor(None, get_next)
            if item is None:
                break
            yield item

    async def _get_document_agent(
        self,
        session_id: str,
        content: str,
        files: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        获取缓存的 DocumentAgent 实例，并将消息携带的文件设置到 agent。
        设计：agent 被 session 复用，对话历史累积；文件跟随消息追加到 agent。
        """
        # 获取或创建缓存的 agent 实例
        agent = _get_cached_agent(session_id, self.config)
        
        # 将消息携带的文件设置到 agent（传入 session_id 以便从数据库查询 file_path）
        if files:
            set_agent_files(agent, files, self.config, session_id)
        
        return agent

    async def chat_stream(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
        progress_callback=None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天响应。
        每次对话都基于当前勾选的文件，支持多轮对话上下文。
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = normalize_chat_mode(str(mode).strip())

        # 默认对话：直连 LLM 流式
        if mode == "default_conversation":
            async for part in self._stream_default_conversation(session_id, pending_user_content=content):
                yield part
            return

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            async for part in self._stream_sync_generator(agent.stream_chat(content)):
                yield part
            return

        # 文档编辑模式：走工作流协调器，返回结构化 JSON（含 output_file 供前端「另存为」）
        if mode == "document_editing":
            import json
            from pathlib import Path as PathLib

            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
            result = await asyncio.to_thread(self.coordinator.execute, task_spec, progress_callback=progress_callback)
            await asyncio.sleep(0)

            message = result.message if result else "文档编辑完成"
            output_file = getattr(result, "output_file", None) if result else None
            inner_data = getattr(result.data, "data", None) if result and result.data else None
            if isinstance(inner_data, dict) and inner_data.get("output_file"):
                output_file = inner_data.get("output_file")

            generated_files: List[Dict[str, Any]] = []
            if output_file and PathLib(str(output_file)).is_file():
                p = PathLib(str(output_file))
                generated_files.append(
                    {
                        "file_path": str(p.resolve()),
                        "file_name": p.name,
                        "file_type": p.suffix.lower().lstrip(".") or "docx",
                    }
                )

            payload = {
                "success": bool(result.success) if result else False,
                "message": message,
                "output_file": str(output_file) if output_file else None,
                "generated_files": generated_files,
            }
            yield json.dumps(payload, ensure_ascii=False)
            return

        # 实体提取模式：返回完整 JSON（非流式），支持进度回调
        if mode == "entity_extraction":
            import json
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)

            result = await asyncio.to_thread(
                self.coordinator.execute,
                task_spec,
                progress_callback=progress_callback,
            )
            await asyncio.sleep(0)

            if mode == "entity_extraction":
                agent_response = result.data if result and result.data else None
                inner_data = agent_response.data if agent_response else {}
                response_data = {
                    "success": result.success if result else False,
                    "message": result.message if result else "实体提取失败",
                    "entities": inner_data.get("entities") if isinstance(inner_data, dict) else [],
                    "schema": inner_data.get("schema") if isinstance(inner_data, dict) else {},
                    "chunk_count": inner_data.get("chunk_count") if isinstance(inner_data, dict) else 0,
                    "total_extractions": inner_data.get("total_extractions") if isinstance(inner_data, dict) else 0,
                }
                yield json.dumps(response_data, ensure_ascii=False)
                return

        # 表格填表模式：返回结构化 JSON（非流式）
        if mode == "table_filling":
            import json
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)

            result = await asyncio.to_thread(
                self.coordinator.execute,
                task_spec,
                progress_callback=progress_callback,
            )
            await asyncio.sleep(0)

            agent_response = result.data if result and result.data else None
            inner_data = agent_response.data if agent_response else {}
            response_data = {
                "success": result.success if result else False,
                "message": result.message if result else "表格填表失败",
                "status": inner_data.get("status") if isinstance(inner_data, dict) else "completed",
                "excel_path": inner_data.get("excel_path") if isinstance(inner_data, dict) else None,
                "output_json": inner_data.get("output_json") if isinstance(inner_data, dict) else None,
                "total_rows": inner_data.get("total_rows") if isinstance(inner_data, dict) else 0,
                "matched_rows": inner_data.get("matched_rows") if isinstance(inner_data, dict) else 0,
                "used_plan": inner_data.get("used_plan") if isinstance(inner_data, dict) else None,
                "plan_source": inner_data.get("plan_source") if isinstance(inner_data, dict) else None,
                "template_filled": inner_data.get("template_filled") if isinstance(inner_data, dict) else False,
                "template_output": inner_data.get("template_output") if isinstance(inner_data, dict) else None,
                "template_mapping": inner_data.get("template_mapping") if isinstance(inner_data, dict) else {},
                "multi_table_results": inner_data.get("multi_table_results") if isinstance(inner_data, dict) else None,
            }
            yield json.dumps(response_data, ensure_ascii=False)
            return

        # 其他模式：工作流协调器（历史兼容）；message 为空时会导致零 chunk，须兜底
        _log.warning(
            "chat_stream_fallback_coordinator mode=%r session_id=%s",
            mode,
            session_id,
        )
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = await asyncio.to_thread(self.coordinator.execute, task_spec)
        msg = (result.message if result else None) or ""
        if not str(msg).strip():
            msg = (
                "（当前模式走了工作流回退分支，但未返回文本。请确认 mode 为 default_conversation / document_understanding 等；"
                "若已确认，请查看 coordinator 日志。）"
            )
        for char in msg:
            yield char
            await asyncio.sleep(0.005)

    async def chat(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        非流式聊天响应
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = normalize_chat_mode(str(mode).strip())

        # 默认对话
        if mode == "default_conversation":
            return await self._get_conversation_response(session_id, pending_user_content=content)

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            return agent.chat(content)

        if mode == "document_editing":
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
            result = await asyncio.to_thread(self.coordinator.execute, task_spec)
            return result.message if result else "文档编辑完成"

        # 其他模式
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = self.coordinator.execute(task_spec)
        return result.message

    async def _get_conversation_response(
        self, session_id: str, pending_user_content: Optional[str] = None
    ) -> str:
        """获取默认对话的完整回复（非流式）"""
        llm = get_llm_service()
        if not llm.is_available():
            return "LLM 服务不可用，请检查 API Key 配置。"

        # 直接传字典列表，llm.chat 内部会进行转换
        messages = self._build_conversation_llm_messages(
            session_id, pending_user_content=pending_user_content
        )
        return llm.chat(messages=messages)

    def _get_task_type(self, mode: str) -> TaskType:
        """将前端模式转换为 TaskType"""
        mapping = {
            "default_conversation": TaskType.DEFAULT_CONVERSATION,
            "document_understanding": TaskType.DOCUMENT_UNDERSTANDING,
            "document_editing": TaskType.DOCUMENT_EDITING,
            "entity_extraction": TaskType.ENTITY_EXTRACTION,
            "table_filling": TaskType.TABLE_FILLING,
        }
        return mapping.get(mode, TaskType.DEFAULT_CONVERSATION)

    def _get_file_type(self, file_name: str) -> FileType:
        """根据文件名判断文件类型"""
        ext = file_name.lower().split('.')[-1]
        mapping = {
            'pdf': FileType.PDF,
            'doc': FileType.DOCX,
            'docx': FileType.DOCX,
            'xls': FileType.XLSX,
            'xlsx': FileType.XLSX,
            'txt': FileType.TXT,
            'md': FileType.MD,
        }
        return mapping.get(ext, FileType.TXT)

    def _build_file_info(self, file_dict: Dict[str, Any], session_id: Optional[str] = None) -> FileInfo:
        """将文件字典转换为 FileInfo"""
        return FileInfo(
            path=_resolve_local_file_path(file_dict, self.config, session_id),
            file_type=self._get_file_type(file_dict.get('file_name', '')),
        )

    def _build_task_spec(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskSpec:
        """构建任务规格"""
        # 获取数据文件
        source_files = [self._build_file_info(f, session_id) for f in files if f.get('is_selected', True)]

        # 获取模板文件
        template_file = None
        if template_files:
            selected_templates = [f for f in template_files if f.get('is_selected', True)]
            if selected_templates:
                template_file = self._build_file_info(selected_templates[0], session_id)

        return TaskSpec(
            task_type=self._get_task_type(mode),
            instruction=content,
            source_files=source_files,
            template_file=template_file,
            session_id=session_id,
        )

    def _build_conversation_llm_messages(
        self,
        session_id: str,
        pending_user_content: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """默认对话：从会话历史构造发给 LLM 的消息列表；可显式带上本轮用户句，避免读库竞态漏句。"""
        system_prompt = get_config().agent.get_prompt("conversation")
        rows = get_messages(session_id, limit=50, config=self.config)
        msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for r in rows:
            if r.role in ("user", "assistant"):
                body = "" if r.content is None else str(r.content)
                msgs.append({"role": r.role, "content": body})
        if pending_user_content is not None and str(pending_user_content).strip() != "":
            pc = str(pending_user_content).strip()
            last = msgs[-1] if len(msgs) > 1 else None
            if not (last and last.get("role") == "user" and str(last.get("content", "")).strip() == pc):
                msgs.append({"role": "user", "content": pending_user_content})
        return msgs

    async def _stream_default_conversation(
        self,
        session_id: str,
        pending_user_content: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """默认对话：真实 LLM 流式输出，保留 Markdown 原文。"""
        llm = get_llm_service()
        if not llm.is_available():
            yield "LLM 服务不可用，请检查 API Key 配置。"
            return

        lc_messages = llm._convert_messages(
            self._build_conversation_llm_messages(
                session_id, pending_user_content=pending_user_content
            )
        )
        prov = (get_config().llm.provider or "").strip().lower()
        raw_base = (llm.config.base_url or llm._get_base_url() or "").strip()

        # DeepSeek v4：思考阶段 delta 常在 reasoning_content；通用 ChatOpenAI 不保证合并到 content，前端会长期收不到 chunk。
        # 使用 langchain_deepseek.ChatDeepSeek；默认关闭思考以尽快输出正文（DEEPSEEK_THINKING=enabled 时保留思考链）。
        thinking = (os.getenv("DEEPSEEK_THINKING") or "disabled").strip().lower()
        think_on = thinking in ("enabled", "on", "true", "1")
        extra_body = None
        if prov == "deepseek" and not think_on:
            extra_body = {"thinking": {"type": "disabled"}}

        timeout = float(get_config().llm.request_timeout_seconds)
        max_retries = int(get_config().llm.max_retries)

        def _normalize_deepseek_api_base(url: str) -> str:
            u = url.strip().rstrip("/")
            if not u:
                return "https://api.deepseek.com/v1"
            low = u.lower()
            if "api.deepseek.com" in low and not low.endswith("/v1"):
                return u + "/v1"
            return u

        client: Any
        if prov == "deepseek":
            try:
                from langchain_deepseek import ChatDeepSeek
            except ImportError:
                ChatDeepSeek = None  # type: ignore[misc, assignment]
            if ChatDeepSeek is not None:
                api_base = _normalize_deepseek_api_base(raw_base) if raw_base else "https://api.deepseek.com/v1"
                ds_kw: Dict[str, Any] = {
                    "api_key": llm._get_api_key(),
                    "api_base": api_base,
                    "model": llm.config.model,
                    "temperature": llm.config.temperature,
                    "max_tokens": llm.config.max_tokens,
                    "streaming": True,
                    "request_timeout": timeout,
                    "max_retries": max_retries,
                }
                if extra_body is not None:
                    ds_kw["extra_body"] = extra_body
                client = ChatDeepSeek(**ds_kw)
                _log.info(
                    "llm_default_stream client=ChatDeepSeek session_id=%s model=%r api_base=%r thinking=%s extra_body=%r api_key=%s",
                    session_id,
                    llm.config.model,
                    api_base,
                    "on" if think_on else "off",
                    extra_body,
                    mask_secret(llm._get_api_key()),
                )
            else:
                _log.warning(
                    "llm_default_stream ChatDeepSeek 未安装，回退 ChatOpenAI session_id=%s（DeepSeek 流式可能无正文）",
                    session_id,
                )
                client_kwargs: Dict[str, Any] = {
                    "api_key": llm._get_api_key(),
                    "base_url": raw_base or llm._get_base_url(),
                    "model": llm.config.model,
                    "temperature": llm.config.temperature,
                    "max_tokens": llm.config.max_tokens,
                    "streaming": True,
                    "request_timeout": timeout,
                    "max_retries": max_retries,
                }
                if extra_body is not None:
                    client_kwargs["extra_body"] = extra_body
                client = ChatOpenAI(**client_kwargs)
                _log.info(
                    "llm_default_stream client=ChatOpenAI(fallback) session_id=%s model=%r base_url=%r api_key=%s",
                    session_id,
                    llm.config.model,
                    raw_base or llm._get_base_url(),
                    mask_secret(llm._get_api_key()),
                )
        else:
            client_kwargs = {
                "api_key": llm._get_api_key(),
                "base_url": raw_base or llm._get_base_url(),
                "model": llm.config.model,
                "temperature": llm.config.temperature,
                "max_tokens": llm.config.max_tokens,
                "streaming": True,
                "request_timeout": timeout,
                "max_retries": max_retries,
            }
            if extra_body is not None:
                client_kwargs["extra_body"] = extra_body
            client = ChatOpenAI(**client_kwargs)
            _log.info(
                "llm_default_stream client=ChatOpenAI session_id=%s provider=%s model=%r base_url=%r api_key=%s extra_body=%r",
                session_id,
                prov,
                llm.config.model,
                raw_base or llm._get_base_url(),
                mask_secret(llm._get_api_key()),
                extra_body,
            )

        _log.info(
            "llm_default_stream_invoke session_id=%s lc_messages=%d user_preview=%r",
            session_id,
            len(lc_messages),
            (pending_user_content or "")[:120],
        )

        def _chunk_to_text(chunk) -> str:
            raw = getattr(chunk, "content", None)
            text = _normalize_ai_content(raw)
            if text:
                return text
            alt = getattr(chunk, "text", None)
            if isinstance(alt, str) and alt.strip():
                return alt
            add_kw = getattr(chunk, "additional_kwargs", None) or {}
            if isinstance(add_kw, dict):
                rc = add_kw.get("reasoning_content")
                if isinstance(rc, str) and rc.strip():
                    return rc
            return ""

        emitted = False
        raw_chunks = 0
        nonempty_chunks = 0
        out_chars = 0
        first_nonempty_idx: Optional[int] = None
        t0 = time.perf_counter()
        try:
            async for chunk in client.astream(lc_messages):
                raw_chunks += 1
                piece = _chunk_to_text(chunk)
                if piece:
                    nonempty_chunks += 1
                    out_chars += len(piece)
                    if first_nonempty_idx is None:
                        first_nonempty_idx = raw_chunks
                    emitted = True
                    yield piece
                elif raw_chunks <= 3 and not piece:
                    add_kw = getattr(chunk, "additional_kwargs", None) or {}
                    _log.info(
                        "llm_default_empty_chunk session_id=%s idx=%s chunk_type=%s add_kw_keys=%s",
                        session_id,
                        raw_chunks,
                        type(chunk).__name__,
                        list(add_kw.keys()) if isinstance(add_kw, dict) else add_kw,
                    )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            _log.exception(
                "llm_default_stream_failed session_id=%s provider=%s model=%r raw_chunks=%s nonempty=%s out_chars=%s elapsed_ms=%s err=%s",
                session_id,
                prov,
                llm.config.model,
                raw_chunks,
                nonempty_chunks,
                out_chars,
                elapsed_ms,
                exc,
            )
            yield f"（调用模型失败：{exc}。请核对 API Key、网络与 base_url；DeepSeek 建议安装 langchain-deepseek 并查看服务端完整报错。）"
            return
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _log.info(
            "llm_default_stream_done session_id=%s provider=%s model=%r raw_chunks=%d nonempty_chunks=%d out_chars=%d first_nonempty_idx=%s emitted=%s elapsed_ms=%d",
            session_id,
            prov,
            llm.config.model,
            raw_chunks,
            nonempty_chunks,
            out_chars,
            first_nonempty_idx,
            emitted,
            elapsed_ms,
        )
        if not emitted:
            _log.warning(
                "llm_default_stream_zero_visible session_id=%s provider=%s model=%r raw_chunks=%d elapsed_ms=%d",
                session_id,
                prov,
                llm.config.model,
                raw_chunks,
                elapsed_ms,
            )
            yield (
                "（模型未返回任何可见内容。请核对：1) LLM_PROVIDER / 模型名与密钥是否同属一家；"
                "2) base_url（DeepSeek OpenAI 兼容建议 https://api.deepseek.com ，程序会自动补 /v1）；"
                "3) 若需官方示例中的思考模式，设置 DEEPSEEK_THINKING=enabled；4) 服务端日志中的上游报错。）"
            )

    def execute_task(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        执行 Agent 任务（非流式）
        """
        task_spec = self._build_task_spec(session_id, mode, content, files, template_files)
        result = self.coordinator.execute(task_spec)

        # 表格填表模式：返回结构化字典
        if mode == "table_filling":
            agent_response = result.data if result.data else None
            inner_data = agent_response.data if agent_response else {}
            return {
                "success": result.success,
                "message": result.message,
                "status": inner_data.get("status") if isinstance(inner_data, dict) else "completed",
                "excel_path": inner_data.get("excel_path") if isinstance(inner_data, dict) else None,
                "output_json": inner_data.get("output_json") if isinstance(inner_data, dict) else None,
                "total_rows": inner_data.get("total_rows") if isinstance(inner_data, dict) else 0,
                "matched_rows": inner_data.get("matched_rows") if isinstance(inner_data, dict) else 0,
                "used_plan": inner_data.get("used_plan") if isinstance(inner_data, dict) else None,
                "plan_source": inner_data.get("plan_source") if isinstance(inner_data, dict) else None,
                "template_filled": inner_data.get("template_filled") if isinstance(inner_data, dict) else False,
                "template_output": inner_data.get("template_output") if isinstance(inner_data, dict) else None,
                "template_mapping": inner_data.get("template_mapping") if isinstance(inner_data, dict) else {},
                "multi_table_results": inner_data.get("multi_table_results") if isinstance(inner_data, dict) else None,
            }

        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "output_file": result.output_file,
        }

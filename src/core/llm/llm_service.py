"""
LLM 服务模块 (LangChain 版本)
统一管理所有 LLM 请求
"""
from typing import Dict, List, Optional, Any, Union, Callable
import re
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import StreamingStdOutCallbackHandler
from langchain_core.callbacks.base import BaseCallbackHandler
from config import get_config, LLMConfig
from utils.logger import get_logger


def _normalize_ai_content(content: Any) -> str:
    """
    LangChain / OpenAI 兼容接口下 content 可能为 str，或块列表
    [{"type":"text","text":"..."}]；统一为纯文本，避免 str += list 抛错。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def strip_markdown(text: str) -> str:
    """移除文本中的markdown格式符号"""
    # 移除粗体、斜体等
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # 移除行内代码
    text = re.sub(r'`(.+?)`', r'\1', text)
    # 移除列表标记
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 移除标题标记
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 移除 emoji
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)
    text = re.sub(r'[\U00002600-\U000027BF]', '', text)
    return text


class MarkdownFilterCallback(BaseCallbackHandler):
    """自定义回调：流式输出时过滤 markdown 格式"""

    def __init__(self, prefix: str = "[系统]: ", on_token: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.prefix = prefix
        self.on_token = on_token
        self._buffer = ""
        self._first = True

    def on_llm_new_token(self, token: Any, **kwargs) -> None:
        """每个新 token 到达时调用"""
        if self._first and self.prefix:
            self._first = False

        self._buffer += _normalize_ai_content(token)

        # 整行处理更干净
        if '\n' in self._buffer:
            lines = self._buffer.rsplit('\n', 1)
            completed_lines = lines[0]
            self._buffer = lines[1] if len(lines) > 1 else ""

            if completed_lines:
                clean = strip_markdown(completed_lines).strip()
                if clean:
                    if self.on_token:
                        self.on_token(clean)

        # 处理最后的 buffer（如果没有换行符）
        if len(self._buffer) > 20:  # 积累足够字符后处理
            clean = strip_markdown(self._buffer).strip()
            if clean:
                # 移除行首可能的列表标记残留
                clean = re.sub(r'^\s*[-*+]\s*', '', clean)
                if clean:
                    if self.on_token:
                        self.on_token(clean)
            self._buffer = ""

    def flush(self):
        """刷新剩余 buffer"""
        if self._buffer:
            clean = strip_markdown(self._buffer).strip()
            if clean:
                if self.on_token:
                    self.on_token(clean)
            self._buffer = ""


class LLMService:
    """
    LLM 服务类 (基于 LangChain)
    提供统一的 LLM 调用接口
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_config().llm
        self.logger = get_logger(__name__)
        self._client: Optional[ChatOpenAI] = None

    def _get_client(self) -> ChatOpenAI:
        """获取或创建 LangChain LLM 客户端"""
        if self._client is None:
            self._client = ChatOpenAI(**self._chat_openai_kwargs())

        return self._client

    def _chat_openai_kwargs(self, **overrides: Any) -> Dict[str, Any]:
        """构造 ChatOpenAI 公共参数（含超时，默认 30 分钟）。"""
        kw: Dict[str, Any] = {
            "api_key": self._get_api_key(),
            "base_url": self._get_base_url(),
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "streaming": self.config.streaming,
            "request_timeout": self.config.request_timeout_seconds,
            "max_retries": self.config.max_retries,
        }
        kw.update(overrides)
        return kw

    def _get_api_key(self) -> str:
        """获取 API Key"""
        return (
            self.config.api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )

    def _get_base_url(self) -> str:
        """获取 API Base URL"""
        if self.config.base_url:
            return self.config.base_url

        provider = self.config.provider.lower()
        if provider == "deepseek":
            return "https://api.deepseek.com/v1"
        elif provider == "openai":
            return "https://api.openai.com/v1"
        elif provider == "anthropic":
            return "https://api.anthropic.com"
        elif "openai" in provider or "compatible" in provider:
            return "https://api.openai.com/v1"

        return ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        strip_markdown_output: bool = True,
    ) -> str:
        """
        发起聊天请求

        Args:
            messages: 消息列表 [{"role": "system|user|assistant", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            strip_markdown_output: 为 False 时保留 Markdown（供前端渲染）

        Returns:
            LLM 响应文本
        """
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("未配置 API Key，请检查环境变量或配置")

        # 转换消息格式
        langchain_messages = self._convert_messages(messages)

        # 创建临时客户端（如果参数不同）
        if model or temperature is not None or max_tokens:
            client = ChatOpenAI(
                **self._chat_openai_kwargs(
                    model=model or self.config.model,
                    temperature=temperature if temperature is not None else self.config.temperature,
                    max_tokens=max_tokens or self.config.max_tokens,
                )
            )
        else:
            client = self._get_client()

        # 根据配置选择流式或普通调用
        if self.config.streaming:
            callback = MarkdownFilterCallback() if strip_markdown_output else None
            return self._stream_invoke(
                client, langchain_messages, callback, strip_markdown_output=strip_markdown_output
            )
        else:
            response = client.invoke(langchain_messages)
            return _normalize_ai_content(response.content)

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[BaseMessage]:
        """转换消息格式为 LangChain 格式"""
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                result.append(SystemMessage(content=content))
            elif role == "user":
                result.append(HumanMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))

        return result

    def chat_with_system(
        self,
        system_prompt: str,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        便捷方法：使用系统提示词和用户输入发起聊天

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            conversation_history: 对话历史
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            LLM 响应文本
        """
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history[-10:])

        messages.append({"role": "user", "content": user_input})

        return self.chat(messages, model, temperature, max_tokens)

    def _stream_invoke(
        self,
        client: ChatOpenAI,
        messages,
        callback: Optional[MarkdownFilterCallback] = None,
        strip_markdown_output: bool = True,
    ) -> str:
        """流式调用并收集完整响应"""
        full_response = ""
        for chunk in client.stream(messages):
            piece = _normalize_ai_content(getattr(chunk, "content", None))
            if piece:
                if callback:
                    callback.on_llm_new_token(piece)
                full_response += piece
        if callback:
            callback.flush()
        return strip_markdown(full_response) if strip_markdown_output else full_response

    def chat_with_history(
        self,
        messages: List[BaseMessage],
        **kwargs
    ) -> str:
        """
        直接使用 LangChain 消息对象进行对话

        Args:
            messages: LangChain 消息列表
            **kwargs: 其他参数

        Returns:
            LLM 响应文本
        """
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("未配置 API Key")

        client = self._get_client()
        response = client.invoke(messages, **kwargs)
        return _normalize_ai_content(response.content)

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        callbacks: Optional[List] = None,
        **kwargs
    ) -> Any:
        """
        流式聊天请求

        Args:
            messages: 消息列表
            callbacks: 回调处理器
            **kwargs: 其他参数

        Returns:
            生成器
        """
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("未配置 API Key")

        langchain_messages = self._convert_messages(messages)

        callbacks = callbacks or [StreamingStdOutCallbackHandler()]
        client = ChatOpenAI(**self._chat_openai_kwargs(streaming=True))

        return client.stream(langchain_messages, callbacks=callbacks)

    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        try:
            api_key = self._get_api_key()
            return bool(api_key)
        except Exception:
            return False

    def get_model_name(self) -> str:
        """获取当前模型名称"""
        return self.config.model


# 全局实例
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """获取全局 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def reset_llm_service() -> None:
    """丢弃缓存的 LLM 客户端，使下次使用当前 get_config().llm。"""
    global _llm_service
    _llm_service = None

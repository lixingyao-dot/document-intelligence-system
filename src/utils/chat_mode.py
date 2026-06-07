"""统一规范化 WebSocket / HTTP 传入的对话模式字符串，避免大小写或别名导致误走「其他模式」分支（零 chunk）。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_KNOWN = frozenset(
    {
        "default_conversation",
        "document_understanding",
        "document_editing",
        "entity_extraction",
        "table_filling",
        "mixed",
    }
)

# 编辑类关键词（触发 document_editing）
_EDIT_KEYWORDS = (
    "替换", "修改", "删除", "加粗", "加下划线", "加斜体", "高亮", "字体",
    "字号", "对齐", "缩进", "行距", "段落", "格式", "样式", "编号",
    "目录", "表格", "页码", "页脚", "列表", "重排", "插入",
    "replace", "bold", "italic", "highlight", "font", "align",
    "indent", "spacing", "format", "style", "heading", "reorder",
    "bullet", "numbered", "list", "insert", "underline",
)

# 问答类关键词（触发 document_understanding）
_QA_KEYWORDS = (
    "总结", "摘要", "要点", "核心", "内容", "什么", "哪些", "怎么",
    "为什么", "解释", "分析", "告诉我", "帮我", "请问", "问题",
    "summary", "summarize", "what", "how", "why", "explain", "tell me",
    "extract", "列出", "描述", "概括",
)


def normalize_chat_mode(mode: Optional[str]) -> str:
    m = str(mode or "").strip().lower()
    if not m:
        return "default_conversation"
    if m in ("default", "chat", "dialog", "conversation"):
        return "default_conversation"
    if m in ("doc_understanding", "document-understanding", "understanding"):
        return "document_understanding"
    if m in ("doc_editing", "document-editing", "editing"):
        return "document_editing"
    if m in ("entity", "extraction"):
        return "entity_extraction"
    if m in ("table", "filling", "fill_table"):
        return "table_filling"
    if m in _KNOWN:
        return m
    return "default_conversation"


def _has_excel_data(data_files: List[Dict[str, Any]]) -> bool:
    """判断数据文件中是否有 Excel 文件。"""
    for f in (data_files or []):
        name = str(f.get("file_name") or "").lower()
        if name.endswith((".xlsx", ".xls", ".csv")):
            return True
    return False


def _rule_based_detect(
    content: str,
    data_files: List[Dict[str, Any]],
    template_files: List[Dict[str, Any]],
) -> str:
    """关键词规则兜底。"""
    text = (content or "").strip().lower()

    if data_files and template_files:
        # Excel 数据源 + 模板 → 直接填表；文档 + 模板 → 先提取再填表
        if _has_excel_data(data_files):
            return "table_filling"
        return "entity_extraction"

    if data_files:
        if any(kw in text for kw in _EDIT_KEYWORDS):
            return "document_editing"
        if any(kw in text for kw in _QA_KEYWORDS):
            return "document_understanding"
        return "document_understanding"

    return "default_conversation"


def _llm_detect_mode(
    content: str,
    data_files: List[Dict[str, Any]],
    template_files: List[Dict[str, Any]],
) -> Optional[str]:
    """用轻量 LLM 调用做意图识别，返回模式或 None（失败时回退规则）。"""
    try:
        from core.llm.llm_service import get_llm_service
        service = get_llm_service()
        if not service or not hasattr(service, "is_available") or not service.is_available():
            return None

        file_names = [f.get("name", "") for f in (data_files or [])[:5]]
        template_names = [f.get("name", "") for f in (template_files or [])[:3]]

        system_prompt = (
            "你是意图分类器。根据用户指令和已上传的文件，判断最合适的处理模式。\n"
            "可选模式：\n"
            "- table_filling：有数据文件+模板文件，需要填表/数据写入模板\n"
            "- document_editing：需要对文档进行修改、格式化、替换、重排等编辑操作\n"
            "- document_understanding：需要阅读文档、回答问题、总结、提取信息\n"
            "- default_conversation：纯聊天，无文件操作\n"
            "\n只输出 JSON：{\"mode\": \"xxx\", \"reason\": \"一句话原因\"}。不要解释。"
        )
        user_prompt = (
            f"用户指令：{content}\n"
            f"数据文件：{file_names or '无'}\n"
            f"模板文件：{template_names or '无'}"
        )

        raw = service.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=128,
        )
        text = (raw or "").strip()
        # 提取 JSON
        m = re.search(r"\{[^{}]+\}", text)
        if m:
            obj = json.loads(m.group(0))
            mode = str(obj.get("mode", "")).strip()
            if mode in _KNOWN:
                logger.info(f"[智能分发-LLM] {mode} ({obj.get('reason', '')})")
                return mode
    except Exception as e:
        logger.debug(f"[智能分发-LLM] 调用失败，回退规则: {e}")
    return None


def auto_detect_mode(
    content: str,
    data_files: List[Dict[str, Any]] | None = None,
    template_files: List[Dict[str, Any]] | None = None,
) -> str:
    """
    智能模式检测：LLM 优先，规则兜底。
    优先级：表格填表 > 文档编辑 > 文档理解 > 默认对话。
    """
    data_files = data_files or []
    template_files = template_files or []

    # 场景一：有数据文件 + 有模板文件 → 根据数据文件类型选择模式
    if data_files and template_files:
        if _has_excel_data(data_files):
            return "table_filling"      # Excel 数据源 + 模板 → 直接填表
        return "entity_extraction"      # 文档 + 模板 → 先提取实体再填表

    # 有文件时，LLM 优先判断
    if data_files:
        llm_result = _llm_detect_mode(content, data_files, template_files)
        if llm_result:
            return llm_result
        return _rule_based_detect(content, data_files, template_files)

    # 无文件 → 默认对话
    return "default_conversation"

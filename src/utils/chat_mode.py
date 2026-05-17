"""统一规范化 WebSocket / HTTP 传入的对话模式字符串，避免大小写或别名导致误走「其他模式」分支（零 chunk）。"""
from __future__ import annotations

from typing import Optional

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
    # 未知字符串（含历史脏数据）一律按默认对话，避免误走 coordinator 且 result.message 为空导致零 chunk
    return "default_conversation"

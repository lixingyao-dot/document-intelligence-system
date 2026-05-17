"""LLM 诊断：密钥脱敏，避免日志泄露完整 API Key。"""
from __future__ import annotations

from typing import Optional


def mask_secret(value: Optional[str], tail: int = 4) -> str:
    if value is None or not str(value).strip():
        return "(empty)"
    s = str(value).strip()
    if len(s) <= tail + 1:
        return "(set)"
    return f"...{s[-tail:]}"

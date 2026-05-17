"""API 用 UTC 时间字符串（始终带 Z 后缀，便于前端按 UTC 解析）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        s = dt.strip()
        if not s:
            return ""
        if s.endswith("Z") or s.endswith("z"):
            return s[:-1] + "Z" if s.endswith("z") else s
        if "+" in s[10:] or "-" in s[10:]:
            try:
                return utc_iso(datetime.fromisoformat(s.replace("Z", "+00:00")))
            except ValueError:
                return s
        return s + "Z"
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"

"""Shared standard style presets for AgentA."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


STANDARD_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "docx": {
        "strategy": "standard",
        "body_font_name": "宋体",
        "body_font_size": 11,
        "heading_font_name": "黑体",
        "heading_font_size": 14,
        "heading_bold": True,
    },
    "xlsx": {
        "strategy": "standard",
        "header_font_name": "Calibri",
        "header_font_size": 11,
        "body_font_name": "Calibri",
        "body_font_size": 11,
        "header_horizontal": "center",
        "body_horizontal": "left",
        "border_style": "thin",
        "border_color": "000000",
    },
    "md": {
        "strategy": "standard",
    },
    "txt": {
        "strategy": "standard",
    },
}


def get_standard_style_preset(file_type: str) -> Dict[str, Any]:
    """Return a copy of the standard style preset for the given file type."""
    return deepcopy(STANDARD_STYLE_PRESETS.get((file_type or "").lower(), {}))

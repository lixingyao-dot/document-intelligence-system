"""ActionPlan model and validation utilities for AgentA."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal

from jsonschema import validate
from pydantic import BaseModel, Field

from .instruction_parser import parse_instruction_with_llm_fallback


class ActionType(str, Enum):
    """Supported action types for document operations."""

    BOLD_HEADING = "bold_heading"
    INSERT_PAGE_NUMBER = "insert_page_number"
    UNIFY_STYLE = "unify_style"
    REORDER_PARAGRAPHS = "reorder_paragraphs"
    BATCH_FORMAT = "batch_format"
    EXTRACT_CONTENT = "extract_content"
    REPLACE_TEXT = "replace_text"
    INSERT_TOC = "insert_toc"
    AUTO_COLUMN_WIDTH = "auto_column_width"
    FREEZE_HEADER_ROW = "freeze_header_row"
    REMOVE_BLANK_LINES = "remove_blank_lines"
    SET_FONT_FAMILY = "set_font_family"
    SET_FONT_COLOR = "set_font_color"
    SET_FONT_SIZE = "set_font_size"
    SET_PARAGRAPH_ALIGNMENT = "set_paragraph_alignment"
    SET_LINE_SPACING = "set_line_spacing"
    SET_FIRST_LINE_INDENT = "set_first_line_indent"
    SET_HIGHLIGHT = "set_highlight"
    INSERT_TABLE = "insert_table"
    INSERT_FOOTER_TEXT = "insert_footer_text"
    SET_HEADING_NUMBERING = "set_heading_numbering"
    SET_ITALIC = "set_italic"
    SET_UNDERLINE = "set_underline"
    SET_PARAGRAPH_SPACING = "set_paragraph_spacing"
    SET_BULLET_LIST = "set_bullet_list"
    SET_NUMBERED_LIST = "set_numbered_list"
    SET_PARAGRAPH_SHADING = "set_paragraph_shading"
    SET_PARAGRAPH_BORDER = "set_paragraph_border"
    ADD_HYPERLINK = "add_hyperlink"


class ActionItem(BaseModel):
    """A single executable action item."""

    action_type: ActionType
    target: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    requires_confirmation: bool = False


class ActionPlan(BaseModel):
    """Top-level normalized action plan."""

    intent: str
    actions: List[ActionItem] = Field(min_length=1)
    target: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    requires_confirmation: bool = False
    file_scope: Literal["md", "xlsx", "docx", "txt", "all"] = "all"


_SCHEMA_PATH = Path(__file__).with_name("action_plan.schema.json")


def get_action_plan_json_schema() -> Dict[str, Any]:
    """Load JSON schema for ActionPlan validation."""
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_action_plan_schema(plan: Dict[str, Any]) -> None:
    """Validate plan against JSON schema; raises on invalid payload."""
    validate(instance=plan, schema=get_action_plan_json_schema())


def build_action_plan_from_instruction(instruction: str, llm_service=None) -> ActionPlan:
    """Build ActionPlan from natural language using LLM-primary parser with safe fallbacks."""
    parsed = parse_instruction_with_llm_fallback(instruction, llm_service=llm_service)

    items = [
        ActionItem(
            action_type=ActionType(a["action_type"]),
            target=a.get("target", {}),
            params=a.get("params", {}),
            confidence=a.get("confidence", 0.9),
            requires_confirmation=a.get("requires_confirmation", False),
        )
        for a in parsed.get("actions", [])
    ]

    return ActionPlan(
        intent=parsed.get("intent", "extract_content"),
        actions=items,
        target=parsed.get("target", {}),
        params=parsed.get("params", {}),
        confidence=parsed.get("confidence", 0.9),
        requires_confirmation=parsed.get("requires_confirmation", False),
        file_scope=parsed.get("file_scope", "all"),
    )

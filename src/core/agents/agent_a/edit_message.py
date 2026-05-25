"""Human-readable summaries for document editing results."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_ACTION_LABELS = {
    "clear_document_content": "清空文档内容",
    "replace_text": "文本替换",
    "bold_heading": "标题加粗",
    "unify_style": "统一样式",
    "remove_blank_lines": "删除空行",
    "extract_content": "内容提取（只读）",
    "set_font_family": "设置字体",
    "set_font_color": "设置字体颜色",
    "set_font_size": "设置字号",
    "set_paragraph_alignment": "设置段落对齐",
    "set_line_spacing": "设置行距",
    "set_first_line_indent": "设置首行缩进",
}


def _normalize_action_type(raw: Any) -> str:
    """将 action_type 统一为 snake_case（兼容 ActionType.SET_FONT_FAMILY 等）。"""
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        raw = raw.value
    s = str(raw).strip()
    if s.startswith("ActionType."):
        s = s.split(".", 1)[1]
    return s.lower()


def summarize_edit_execution(instruction: str, execution_report: Optional[List[Dict[str, Any]]]) -> str:
    report = execution_report or []
    if not report:
        return "文档编辑完成，已生成可下载文件。"

    edit_cues = bool(
        re.search(r"删除|清空|清除|改成|改为|替换|加粗|格式|移动|插入", instruction or "", re.IGNORECASE)
    )
    action_types = [_normalize_action_type(item.get("action_type")) for item in report]
    only_extract = action_types and all(t == "extract_content" for t in action_types)

    if only_extract and edit_cues:
        return (
            "未能将你的指令识别为可执行的编辑操作，文档内容未修改。"
            "请改用更明确的表述，例如：「删除文件中的内容」「把张三改成李四」「一级标题加粗」。"
        )

    if re.search(r"(?:输出)?(?:文件)?名(?:字)?改为\s*([^\s，。,；;]+)", instruction or "", re.IGNORECASE):
        if not report or only_extract:
            name_match = re.search(
                r"(?:输出)?(?:文件)?名(?:字)?改为\s*([^\s，。,；;]+)",
                instruction or "",
                re.IGNORECASE,
            )
            new_name = name_match.group(1).strip() if name_match else ""
            if new_name:
                return f"文档已另存为「{new_name}」（正文未改动）。"

    parts: List[str] = []
    for item in report:
        action_type = _normalize_action_type(item.get("action_type"))
        if not item.get("success"):
            parts.append(f"{_ACTION_LABELS.get(action_type, action_type)}：失败")
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        label = _ACTION_LABELS.get(action_type, action_type)
        if action_type == "set_font_family":
            font_name = details.get("font_name") or "宋体"
            parts.append(f"{label}：正文已设为 {font_name}")
            continue
        if action_type == "set_font_color":
            parts.append(f"{label}：完成")
            continue
        if action_type == "set_font_size":
            size_pt = details.get("size_pt")
            parts.append(f"{label}：{size_pt}pt" if size_pt is not None else f"{label}：完成")
            continue
        if action_type == "clear_document_content":
            parts.append(
                f"{label}：已清空 {details.get('cleared_paragraphs', 0)} 段正文"
                f"（表格单元格 {details.get('cleared_table_cells', 0)} 个）"
            )
        elif action_type == "replace_text":
            parts.append(
                f"{label}：替换 {details.get('replaced', 0)} 处"
                f"（「{details.get('find', '')}」→「{details.get('replace', '')}」）"
            )
        else:
            parts.append(f"{label}：完成")

    summary = "；".join(parts)
    return f"文档编辑完成：{summary}。已生成可下载文件。"

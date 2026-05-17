"""Rule-first instruction parser for AgentA."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal

from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from rapidfuzz import fuzz

from core.llm.llm_service import get_llm_service
from utils.logger import get_logger


SUPPORTED_ACTIONS = {
    "bold_heading": {
        "keywords": [
            "标题加粗",
            "加粗标题",
            "标题改粗体",
            "标题设为粗体",
            "heading bold",
            "标题粗体化",
            "标题统一加粗",
            "改成粗体",
        ],
        "patterns": [
            r"(?:把|将)?(?:所有)?(?:[一二三四五六七八九\d]+级)?标题(?:都)?(?:加粗|改为粗体|设为粗体)",
            r"(?:加粗|粗体化).{0,6}标题",
            r"标题.{0,3}(?:改成|改为).{0,2}粗体",
        ],
    },
    "insert_page_number": {
        "keywords": ["页码", "插入页码", "每页页码", "page number", "加页码"],
        "patterns": [
            r"(?:给|为)?(?:每页|每一页|文档).{0,4}(?:加|插入|添加).{0,4}页码",
            r"页码",
        ],
    },
    "unify_style": {
        "keywords": ["样式统一", "统一样式", "统一风格", "统一格式风格", "格式统一", "文件格式化", "统一文件格式", "整体格式化", "标准格式", "规范格式"],
        "patterns": [
            r"(?:统一|标准化).{0,8}(?:样式|风格|格式)",
            r"(?:样式|风格|格式).{0,6}(?:统一|一致)",
            r"格式.{0,3}(?:都)?标准化",
            r"(?:文件|全文|整体).{0,6}(?:格式化|统一格式)",
        ],
    },
    "reorder_paragraphs": {
        "keywords": ["段落重排", "重排段落", "调整段落顺序", "段落换位", "移动第", "移到第", "移动到第", "行移动", "移动行"],
        "patterns": [
            r"(?:从)?第\s*\d+\s*(?:段|行)(?:移动|挪到|放到|调到|到).{0,8}第\s*\d+\s*(?:段|行)",
            r"(?:从)?第\s*[一二三四五六七八九十\d]+\s*(?:段|行)(?:移动|挪到|放到|调到|到|移到).{0,8}第\s*[一二三四五六七八九十\d]+\s*(?:段|行)(?:之后)?",
            r"(?:重排|调整).{0,6}段落",
        ],
    },
    "batch_format": {
        "keywords": ["批量格式化", "批量格式", "批量统一格式", "批量处理格式", "一键格式化"],
        "patterns": [
            r"批量.{0,6}(?:格式|格式化)",
            r"一键.{0,6}格式化",
        ],
    },
    "extract_content": {
        "keywords": ["内容提取", "提取内容", "抽取", "提取", "字段提取", "信息提取", "捞出来", "结构化结果", "结构化"],
        "patterns": [
            r"(?:提取|抽取).{0,20}",
            r"内容提取",
            r"(?:捞出来|捞出).{0,20}",
            r"结构化结果",
        ],
    },
    "replace_text": {
        "keywords": ["替换", "查找替换", "批量替换", "replace text", "统一换成", "统一改成", "都换成", "改为", "改成"],
        "patterns": [
            r"(?:将|把).+?替换为.+",
            r"查找.+替换.+",
            r"批量替换",
            r"(?:将|把).+?(?:统一)?换成.+",
            r"(?:将|把).+?改为.+",
            r"(?:文件)?名(?:字)?改为.+",
        ],
    },
    "insert_toc": {
        "keywords": ["目录", "插入目录", "生成目录", "toc"],
        "patterns": [
            r"(?:插入|生成|添加).{0,4}目录",
            r"目录",
        ],
    },
    "auto_column_width": {
        "keywords": ["自动列宽", "自适应列宽", "调整列宽", "auto column width"],
        "patterns": [
            r"(?:自动|自适应).{0,4}列宽",
            r"调整.{0,4}列宽",
        ],
    },
    "freeze_header_row": {
        "keywords": ["冻结首行", "冻结表头", "冻结标题行", "freeze header"],
        "patterns": [
            r"冻结.{0,4}(?:首行|表头|标题行)",
            r"固定.{0,4}(?:首行|表头)",
        ],
    },
    "clear_document_content": {
        "keywords": [
            "清空文档",
            "清空内容",
            "删除全部内容",
            "删除文档内容",
            "删除文件内容",
            "清除内容",
            "清空正文",
            "clear content",
        ],
        "patterns": [
            r"删除(?:文件|文档)?(?:中|里|内)?的?内容",
            r"清空(?:文件|文档|正文|全部)(?:内容)?",
            r"清除(?:文件|文档)?(?:中|里)?(?:的)?内容",
            r"删除(?:全部|所有)(?:正文|内容)",
        ],
    },
    "remove_blank_lines": {
        "keywords": ["删除空行", "去掉空行", "清理空行", "remove blank lines"],
        "patterns": [
            r"(?:删除|去掉|清理).{0,4}空行",
            r"空行",
        ],
    },
    "set_font_family": {
        "keywords": ["字体", "字体改为", "设置字体", "宋体", "黑体", "楷体", "仿宋", "微软雅黑", "times new roman"],
        "patterns": [
            r"(?:字体|font).{0,8}(?:改为|设为|设置为|换成)",
            r"(?:改成|设置成).{0,6}(?:宋体|黑体|楷体|仿宋|微软雅黑|Times New Roman)",
        ],
    },
    "set_font_color": {
        "keywords": ["字体颜色", "文字颜色", "颜色改为", "红色", "蓝色", "黑色", "绿色", "紫色", "紫", "font color"],
        "patterns": [
            r"(?:字体|文字).{0,4}颜色",
            r"(?:颜色|color).{0,6}(?:改为|设为|设置为|换成)",
        ],
    },
    "set_font_size": {
        "keywords": ["字号", "字体大小", "字大小", "小四", "五号"],
        "patterns": [
            r"(?:字号|字体大小|字大小)",
            r"(?:小四|四号|五号|六号|七号|八号)",
            r"(?:字体|字号|字大|字体大小).{0,4}(\d+\s*磅)",  # 必须在"字体"后面
        ],
    },
    "set_paragraph_alignment": {
        "keywords": ["左对齐", "右对齐", "居中", "两端对齐", "对齐方式"],
        "patterns": [
            r"(?:左对齐|右对齐|居中|两端对齐)",
            r"(?:段落|正文).{0,6}对齐",
        ],
    },
    "set_line_spacing": {
        "keywords": ["行距", "1.5倍", "双倍行距", "单倍行距", "行间距"],
        "patterns": [
            r"(?:行距|行间距)",
            r"(?:单倍|1\.0倍|1\.5倍|2倍|双倍).{0,3}行距",
        ],
    },
    "set_first_line_indent": {
        "keywords": ["首行缩进", "首行缩进2字符", "段首缩进", "首行空两格", "first line indent"],
        "patterns": [
            r"(?:首行|段首).{0,4}缩进",
            r"首行空两格",
        ],
    },
    "set_highlight": {
        "keywords": ["高亮", "高亮标记", "强调", "标记", "highlight", "yellow"],
        "patterns": [
            r"(?:标记|高亮|强调).{0,6}(?:修改|替换|文本|内容)",
            r"(?:替换|查找替换|replace).+(?:并|且|同时).{0,2}(?:高亮|标记|强调)",
        ],
    },
    "insert_table": {
        "keywords": ["插入表格", "添加表格", "创建表格", "新建表格", "insert table", "add table"],
        "patterns": [
            r"(?:插入|添加|创建|新建).{0,2}表格",
            r"\d+\s*[x×xX]\s*\d+.{0,4}表格",
        ],
    },
    "insert_footer_text": {
        "keywords": ["页脚", "页脚文本", "页脚信息", "插入页脚", "footer", "page footer"],
        "patterns": [
            r"(?:页脚|页脚文本).{0,8}(?:插入|添加)",
            r"(?:全文|文档).{0,3}页数|页内容",
        ],
    },
    "set_heading_numbering": {
        "keywords": ["自动编号", "章节编号", "一级标题编号", "标题编号", "numbering", "auto number"],
        "patterns": [
            r"(?:一级)?(?:标题|表题).{0,3}(?:自动)?编号",
            r"(?:章节).*?(?:编号|编号为|format)",
        ],
    },
    "set_italic": {
        "keywords": ["斜体", "意大利体", "italic", "倾斜"],
        "patterns": [
            r"(?:设为|改为|改成)斜体",
            r"(?:加|应用|设置).{0,3}斜体",
        ],
    },
    "set_underline": {
        "keywords": ["下划线", "underline", "加下划线", "带下划线"],
        "patterns": [
            r"(?:加|添加).{0,3}下划线",
            r"(?:设为|改为|改成).{0,3}下划线",
        ],
    },
    "set_paragraph_spacing": {
        "keywords": ["段落间距", "段前距离", "段后距离", "段间距", "paragraph spacing"],
        "patterns": [
            r"(?:段落|段).{0,6}(?:间距|距离|前距|后距)",
            r"(?:段前|段后).{0,3}距离",
        ],
    },
    "set_bullet_list": {
        "keywords": ["项目符号", "符号列表", "bullet points", "列表"],
        "patterns": [
            r"(?:添加|应用|设置).{0,3}(?:项目符号|符号列表)",
            r"(?:改成|设为).{0,3}(?:项目符号|列表)",
        ],
    },
    "set_numbered_list": {
        "keywords": ["编号列表", "编号", "编号序列", "自动编号", "numbered list"],
        "patterns": [
            r"(?:添加|应用|设置).{0,3}(?:编号列表|自动编号)",
            r"(?:改成|设为).{0,3}编号",
        ],
    },
    "set_paragraph_shading": {
        "keywords": ["段落底纹", "背景色", "底纹", "shading", "段落背景"],
        "patterns": [
            r"(?:添加|设置|应用).{0,3}段落底纹",
            r"(?:段落|正文).{0,3}(?:背景|底纹)",
        ],
    },
    "set_paragraph_border": {
        "keywords": ["段落边框", "边框", "边线", "paragraph border"],
        "patterns": [
            r"(?:添加|设置|应用).{0,3}段落边框",
            r"(?:段落|正文).{0,3}边框",
        ],
    },
    "add_hyperlink": {
        "keywords": ["超链接", "添加链接", "链接", "hyperlink", "网址"],
        "patterns": [
            r"(?:添加|创建|设置).{0,3}超链接",
            r"(?:添加|创建).{0,3}链接",
        ],
    },
}


_FILE_SCOPE_KEYWORDS = {
    "md": ["md", "markdown"],
    "xlsx": ["xlsx", "excel", "表格"],
    "docx": ["docx", "word"],
    "txt": ["txt", "文本"],
}


_ACTION_TYPE_ALIASES = {
    "boldheading": "bold_heading",
    "bold_title": "bold_heading",
    "insertpagenumber": "insert_page_number",
    "insert_page_numbers": "insert_page_number",
    "insert_page_num": "insert_page_number",
    "page_number": "insert_page_number",
    "unifystyle": "unify_style",
    "style_unify": "unify_style",
    "reorderparagraphs": "reorder_paragraphs",
    "reorder_paragraph": "reorder_paragraphs",
    "batchformat": "batch_format",
    "batch_formatting": "batch_format",
    "extractcontent": "extract_content",
    "content_extract": "extract_content",
    "extract": "extract_content",
    "replace": "replace_text",
    "search_replace": "replace_text",
    "inserttoc": "insert_toc",
    "table_of_contents": "insert_toc",
    "autocolumnwidth": "auto_column_width",
    "freezeheaderrow": "freeze_header_row",
    "removeblanklines": "remove_blank_lines",
    "clearcontent": "clear_document_content",
    "clear_document": "clear_document_content",
    "清空内容": "clear_document_content",
    "删除内容": "clear_document_content",
    "setfontfamily": "set_font_family",
    "font_family": "set_font_family",
    "setfontcolor": "set_font_color",
    "font_color": "set_font_color",
    "setfontsize": "set_font_size",
    "font_size": "set_font_size",
    "setparagraphalignment": "set_paragraph_alignment",
    "paragraph_alignment": "set_paragraph_alignment",
    "setlinespacing": "set_line_spacing",
    "line_spacing": "set_line_spacing",
    "setfirstlineindent": "set_first_line_indent",
    "first_line_indent": "set_first_line_indent",
    "sethighlight": "set_highlight",
    "highlight": "set_highlight",
    "highlight_text": "set_highlight",
    "inserttable": "insert_table",
    "insert_table": "insert_table",
    "add_table": "insert_table",
    "insertfootertext": "insert_footer_text",
    "insert_footer_text": "insert_footer_text",
    "setheadingnumbering": "set_heading_numbering",
    "set_heading_numbering": "set_heading_numbering",
    "heading_numbering": "set_heading_numbering",
    "标题加粗": "bold_heading",
    "插入页码": "insert_page_number",
    "统一样式": "unify_style",
    "段落重排": "reorder_paragraphs",
    "批量格式化": "batch_format",
    "内容提取": "extract_content",
    "查找替换": "replace_text",
    "插入目录": "insert_toc",
    "自动列宽": "auto_column_width",
    "冻结表头": "freeze_header_row",
    "删除空行": "remove_blank_lines",
    "设置字体": "set_font_family",
    "设置字体颜色": "set_font_color",
    "设置字号": "set_font_size",
    "设置对齐": "set_paragraph_alignment",
    "设置行距": "set_line_spacing",
    "首行缩进": "set_first_line_indent",
    "高亮": "set_highlight",
    "高亮标记": "set_highlight",
    "标记修改": "set_highlight",
    "插入表格": "insert_table",
    "添加表格": "insert_table",
    "创建表格": "insert_table",
    "页脚": "insert_footer_text",
    "页脚信息": "insert_footer_text",
    "页脚文本": "insert_footer_text",
    "自动编号": "set_heading_numbering",
    "斜体": "set_italic",
    "italic": "set_italic",
    "下划线": "set_underline",
    "underline": "set_underline",
    "段落间距": "set_paragraph_spacing",
    "paragraph_spacing": "set_paragraph_spacing",
    "项目符号": "set_bullet_list",
    "bullet_list": "set_bullet_list",
    "编号列表": "set_numbered_list",
    "numbered_list": "set_numbered_list",
    "底纹": "set_paragraph_shading",
    "段落底纹": "set_paragraph_shading",
    "paragraph_shading": "set_paragraph_shading",
    "段落边框": "set_paragraph_border",
    "paragraph_border": "set_paragraph_border",
    "边框": "set_paragraph_border",
    "超链接": "add_hyperlink",
    "hyperlink": "add_hyperlink",
    "一级标题编号": "set_heading_numbering",
    "章节编号": "set_heading_numbering",
}


_ALLOWED_ACTION_TYPES = {
    "bold_heading",
    "insert_page_number",
    "unify_style",
    "reorder_paragraphs",
    "batch_format",
    "extract_content",
    "replace_text",
    "insert_toc",
    "auto_column_width",
    "freeze_header_row",
    "clear_document_content",
    "remove_blank_lines",
    "set_font_family",
    "set_font_color",
    "set_font_size",
    "set_paragraph_alignment",
    "set_line_spacing",
    "set_first_line_indent",
    "set_highlight",
    "insert_table",
    "insert_footer_text",
    "set_heading_numbering",
}


def parse_instruction_rule_first(instruction: str, llm_service=None) -> Dict[str, Any]:
    """Parse instruction using rule-first strategy with fuzzy fallback."""
    payload = _build_rule_payload(instruction, llm_service)
    if payload is not None:
        return payload

    text = (instruction or "").strip()
    return {
        "intent": "extract_content",
        "actions": [_build_action_payload("extract_content", text, fallback=True, llm_service=llm_service)],
        "target": {"scope": "document"},
        "params": {"raw_instruction": text},
        "confidence": 0.7,
        "requires_confirmation": False,
        "file_scope": _detect_file_scope(text.lower()),
    }


def parse_instruction_with_llm_fallback(instruction: str, llm_service=None) -> Dict[str, Any]:
    """
    Parse instruction with LLM-primary strategy and rule fallback.

    Flow:
    1) Call LLM for strict JSON action plan first.
    2) Validate with schema; retry once on invalid response.
    3) If LLM unavailable/invalid => fallback to rule parser.
    4) Rule also misses => fallback to manual-confirmation payload.
    """
    service = llm_service or get_llm_service()
    llm_available = bool(service and hasattr(service, "is_available") and service.is_available())

    if llm_available:
        for attempt in range(2):
            try:
                raw = _call_llm_for_action_plan_json(instruction, service, retry=attempt == 1)
            except Exception:
                continue

            parsed = _safe_load_json(raw)
            if not isinstance(parsed, dict):
                continue

            parsed = _normalize_llm_payload(parsed, instruction)

            parsed.setdefault("target", {"scope": "document"})
            parsed.setdefault("params", {"raw_instruction": instruction})
            parsed.setdefault("file_scope", _detect_file_scope((instruction or "").lower()))

            if _is_valid_action_plan_payload(parsed):
                # 兜底一致性校验：当规则可稳定命中且与 LLM 动作完全不重合时，优先规则结果。
                rule_payload = _build_rule_payload(instruction, service)
                if rule_payload is not None:
                    if _looks_like_multi_step_instruction(instruction):
                        return rule_payload
                    if _should_prefer_rule_over_llm(parsed, rule_payload):
                        return rule_payload
                    if _should_prefer_rule_by_instruction_coverage(instruction, parsed, rule_payload):
                        return rule_payload
                return parsed

    rule_payload = _build_rule_payload(instruction, service)
    if rule_payload is not None:
        return rule_payload

    if llm_available:
        return _manual_confirmation_payload(instruction, "LLM 输出不合法，且规则未命中，已回退人工确认")
    return _manual_confirmation_payload(instruction, "LLM 服务不可用，且规则未命中，已回退人工确认")


def _is_standalone_output_rename(text: str) -> bool:
    """仅重命名输出文件（非正文替换）。"""
    if not re.search(r"(?:输出)?(?:文件)?名(?:字)?改为\s*[^\s，。,；;]+", text or "", flags=re.IGNORECASE):
        return False
    if re.search(r"(?:将|把)\s*\S+\s*改为", text or ""):
        return False
    return True


def _build_rule_payload(instruction: str, llm_service=None) -> Dict[str, Any] | None:
    """Return payload when rule engine can confidently hit; otherwise None."""
    text = (instruction or "").strip()
    lowered = text.lower()

    if _is_standalone_output_rename(text):
        return {
            "intent": "rename_output",
            "actions": [],
            "target": {"scope": "document"},
            "params": {"raw_instruction": text},
            "confidence": 0.92,
            "requires_confirmation": False,
            "file_scope": _detect_file_scope(lowered),
        }

    actions: List[Dict[str, Any]] = []
    segments = _split_instruction_segments(text)

    # 按用户子指令顺序生成动作，保证后续执行是“前一条结果 -> 后一条输入”。
    for seg in segments:
        for action_type, rule in SUPPORTED_ACTIONS.items():
            if not _segment_matches_action(action_type, rule, seg):
                continue

            if action_type == "bold_heading":
                built = _build_bold_heading_actions(seg)
            else:
                built = [_build_action_payload(action_type, seg, llm_service=llm_service)]

            for action in built:
                params = action.get("params") if isinstance(action.get("params"), dict) else {}
                params.setdefault("__segment_text", seg)
                action["params"] = params
                actions.append(action)

    if not actions:
        return None

    actions = _deduplicate_actions(actions)
    actions = _post_process_actions(actions, text)

    confidence = round(sum(a["confidence"] for a in actions) / len(actions), 3)
    requires_confirmation = any(a["requires_confirmation"] for a in actions)
    intent = actions[0]["action_type"] if len(actions) == 1 else "mixed_operations"

    return {
        "intent": intent,
        "actions": actions,
        "target": {"scope": "document"},
        "params": {"raw_instruction": text},
        "confidence": confidence,
        "requires_confirmation": requires_confirmation,
        "file_scope": _detect_file_scope(lowered),
    }


def _extract_action_types(payload: Dict[str, Any]) -> set[str]:
    """从 payload 提取动作类型集合。"""
    actions = payload.get("actions") if isinstance(payload, dict) else None
    if isinstance(actions, list) and actions:
        result: set[str] = set()
        for action in actions:
            if isinstance(action, dict):
                action_type = str(action.get("action_type") or "").strip()
                if action_type:
                    result.add(action_type)
        if result:
            return result

    intent = str((payload or {}).get("intent") or "").strip()
    return {intent} if intent else set()


def _should_prefer_rule_over_llm(llm_payload: Dict[str, Any], rule_payload: Dict[str, Any]) -> bool:
    """
    判定是否应优先规则结果：
    - 规则和 LLM 都有动作集合
    - 且二者没有任何交集
    这通常表示 LLM 输出虽合法，但与当前指令语义偏离。
    """
    llm_types = _extract_action_types(llm_payload)
    rule_types = _extract_action_types(rule_payload)
    if not llm_types or not rule_types:
        return False
    return len(llm_types.intersection(rule_types)) == 0


def _should_prefer_rule_by_instruction_coverage(instruction: str, llm_payload: Dict[str, Any], rule_payload: Dict[str, Any]) -> bool:
    """当指令包含明确操作词且规则覆盖更多时，优先规则结果。"""
    text = instruction or ""
    llm_types = _extract_action_types(llm_payload)
    rule_types = _extract_action_types(rule_payload)

    expected: set[str] = set()
    hints = {
        "set_italic": r"斜体|italic",
        "set_underline": r"下划线|underline",
        "set_highlight": r"高亮|标记",
        "reorder_paragraphs": r"移到|移动|挪到|重排",
        "set_paragraph_border": r"段落边框|边框",
        "set_paragraph_shading": r"段落底纹|底纹|背景色",
        "insert_footer_text": r"页脚|footer",
    }

    for action_type, pattern in hints.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            expected.add(action_type)

    if not expected:
        return False

    llm_hit = len(expected.intersection(llm_types))
    rule_hit = len(expected.intersection(rule_types))
    return rule_hit > llm_hit


def _looks_like_multi_step_instruction(instruction: str) -> bool:
    text = instruction or ""
    if re.search(r"(?:^|\n)\s*(?:\d+|[一二三四五六七八九十]+)\s*[\.、）)]", text):
        return True
    segments = _split_instruction_segments(text)
    return len(segments) >= 3


def _call_llm_for_action_plan_json(instruction: str, llm_service, retry: bool = False) -> str:
    schema = _load_action_plan_schema_text()
    retry_note = "请修复并仅输出合法 JSON。" if retry else ""

    system_prompt = (
        "你是文档指令解析器。"
        "只输出一个 JSON 对象，不要 markdown，不要解释，不要多余文本。"
        "JSON 必须符合给定 schema。"
    )
    user_prompt = (
        f"用户指令: {instruction}\n"
        f"输出 schema: {schema}\n"
        "可用 action_type: bold_heading, insert_page_number, unify_style, reorder_paragraphs, batch_format, extract_content, replace_text, insert_toc, auto_column_width, freeze_header_row, clear_document_content, remove_blank_lines, set_font_family, set_font_color, set_font_size, set_paragraph_alignment, set_line_spacing, set_first_line_indent, set_highlight, insert_table, insert_footer_text, set_heading_numbering\n"
        "字段要求: intent, actions, target, params, confidence, requires_confirmation, file_scope\n"
        "confidence 范围 [0,1]，file_scope 取值 md/xlsx/docx/txt/all。\n"
        f"{retry_note}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 对结构化解析使用低温，并关闭流式以避免 markdown 清洗破坏 JSON（例如下划线）。
    original_streaming = None
    can_toggle_streaming = hasattr(llm_service, "config") and hasattr(llm_service.config, "streaming")
    if can_toggle_streaming:
        original_streaming = llm_service.config.streaming
        llm_service.config.streaming = False

    try:
        return llm_service.chat(messages=messages, temperature=0)
    finally:
        if can_toggle_streaming:
            llm_service.config.streaming = original_streaming


def _safe_load_json(text: str) -> Dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _is_valid_action_plan_payload(payload: Dict[str, Any]) -> bool:
    try:
        jsonschema_validate(instance=payload, schema=_load_action_plan_schema())
        return True
    except JsonSchemaValidationError:
        return False


def _normalize_llm_payload(payload: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(payload)

    normalized["intent"] = str(normalized.get("intent", "extract_content"))
    normalized["target"] = _normalize_action_target_payload(
        normalized.get("target") if isinstance(normalized.get("target"), dict) else {"scope": "document"},
        instruction,
    )
    normalized["params"] = normalized.get("params") if isinstance(normalized.get("params"), dict) else {}
    normalized["params"].setdefault("raw_instruction", instruction)

    normalized["file_scope"] = _normalize_file_scope(normalized.get("file_scope"), instruction)
    normalized["confidence"] = _normalize_confidence(normalized.get("confidence"), default=0.8)
    normalized["requires_confirmation"] = _normalize_bool(normalized.get("requires_confirmation"), default=False)

    raw_actions = normalized.get("actions")
    if not isinstance(raw_actions, list):
        raw_actions = []

    actions: List[Dict[str, Any]] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action_type = _normalize_action_type(item.get("action_type"))
        if action_type is None:
            continue
        raw_params = item.get("params") if isinstance(item.get("params"), dict) else {}
        raw_target = item.get("target") if isinstance(item.get("target"), dict) else {}
        normalized_target = _normalize_action_target(action_type, raw_target, instruction)
        action = {
            "action_type": action_type,
            "target": normalized_target,
            "params": _normalize_action_params(action_type, raw_params, instruction),
            "confidence": _normalize_confidence(item.get("confidence"), default=normalized["confidence"]),
            "requires_confirmation": _normalize_bool(item.get("requires_confirmation"), default=normalized["requires_confirmation"]),
        }
        actions.append(action)

    if not actions:
        actions = [_build_action_payload("extract_content", instruction, fallback=True)]

    actions = _expand_bold_heading_levels(actions, instruction)
    actions = _post_process_actions(actions, instruction)

    normalized["actions"] = actions
    return normalized


def _normalize_action_target_payload(target: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(target or {})

    target_type = str(normalized.get("type", "")).strip().lower()
    if target_type == "paragraph":
        index_value = normalized.get("index", normalized.get("paragraph_index", -1))
        try:
            paragraph_index = int(index_value)
        except Exception:
            paragraph_index = -1
        if paragraph_index >= 0:
            normalized["scope"] = "paragraph"
            normalized["paragraph_index"] = paragraph_index
            normalized["paragraph_index_basis"] = str(normalized.get("paragraph_index_basis", "body") or "body")
            normalized.pop("type", None)
            normalized.pop("index", None)

    if "paragraph_index" in normalized:
        try:
            paragraph_index = int(normalized.get("paragraph_index", -1))
        except Exception:
            paragraph_index = -1
        if paragraph_index >= 0:
            normalized["scope"] = normalized.get("scope") or "paragraph"
            normalized["paragraph_index"] = paragraph_index
            normalized["paragraph_index_basis"] = str(normalized.get("paragraph_index_basis", "body") or "body")

    if normalized.get("scope") == "document":
        return normalized

    section_title = str(normalized.get("section_title", "")).strip()
    if not section_title:
        section_title = _extract_section_heading(instruction)
    if section_title and normalized.get("scope") in {"paragraph", "selective", "all", None, ""}:
        normalized["scope"] = "section_content"
        normalized["section_title"] = section_title

    return normalized


def _normalize_action_type(value: Any) -> str | None:
    if value is None:
        return None

    raw = str(value).strip()
    compact = raw.lower().strip()
    compact = compact.replace("-", "_").replace(" ", "_")
    compact = re.sub(r"[^a-z_\u4e00-\u9fff]", "", compact)

    if compact in _ALLOWED_ACTION_TYPES:
        return compact
    if compact in _ACTION_TYPE_ALIASES:
        return _ACTION_TYPE_ALIASES[compact]

    compact_no_underscore = compact.replace("_", "")
    if compact_no_underscore in _ACTION_TYPE_ALIASES:
        return _ACTION_TYPE_ALIASES[compact_no_underscore]

    return None


def _normalize_action_params(action_type: str, params: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    normalized = dict(params or {})

    if action_type == "reorder_paragraphs":
        def _safe_int(v: Any) -> int:
            try:
                return int(v)
            except Exception:
                return 0

        from_idx = _safe_int(normalized.get("from") or normalized.get("source") or normalized.get("src"))
        to_idx = _safe_int(normalized.get("to") or normalized.get("target") or normalized.get("dst") or normalized.get("dest"))

        # 兼容 LLM 常见输出：{"new_order": [3,1,2]} 或 {"new_order": [3,1]}
        if (from_idx <= 0 or to_idx <= 0) and isinstance(normalized.get("new_order"), list):
            arr = normalized.get("new_order")
            if len(arr) >= 2:
                from_idx = _safe_int(arr[0])
                to_idx = _safe_int(arr[1])

        # 仍未提取到则回退规则解析。
        if from_idx <= 0 or to_idx <= 0:
            r_from, r_to = _extract_reorder_indices(instruction)
            if from_idx <= 0:
                from_idx = r_from
            if to_idx <= 0:
                to_idx = r_to

        normalized["from"] = from_idx
        normalized["to"] = to_idx
        normalized["index_basis"] = str(normalized.get("index_basis", "body_paragraph") or "body_paragraph")
        return normalized

    if action_type == "replace_text":
        find_text = normalized.get("find") or normalized.get("old_text") or normalized.get("source") or ""
        replace_text = normalized.get("replace") or normalized.get("new_text") or normalized.get("target") or ""
        if not find_text or not replace_text:
            fallback_find, fallback_replace = _extract_replace_pair(instruction)
            find_text = find_text or fallback_find
            replace_text = replace_text or fallback_replace
        normalized["find"] = str(find_text)
        normalized["replace"] = str(replace_text)
        return normalized

    if action_type == "unify_style":
        normalized["strategy"] = str(normalized.get("strategy") or "standard")
        normalized["style_preset"] = str(normalized.get("style_preset") or "standard")
        return normalized

    if action_type == "set_font_family":
        font_name = normalized.get("font_name") or normalized.get("font_family") or normalized.get("font") or ""
        if not font_name:
            font_name = _extract_font_name(instruction)
        normalized["font_name"] = str(font_name)
        return normalized

    if action_type == "set_font_color":
        color = normalized.get("color") or normalized.get("font_color") or normalized.get("color_hex") or ""
        if color:
            color = _extract_font_color(str(color))
        else:
            color = _extract_font_color(instruction)
        normalized["color"] = str(color)
        return normalized

    if action_type == "set_font_size":
        size = normalized.get("size_pt")
        if size is None:
            size = normalized.get("font_size")
        if size is None:
            size = normalized.get("size")
        if size is None:
            size = _extract_font_size_pt(instruction)
        try:
            normalized["size_pt"] = float(size)
        except Exception:
            normalized["size_pt"] = float(_extract_font_size_pt(str(size)))
        return normalized

    if action_type == "set_paragraph_alignment":
        alignment = normalized.get("alignment") or normalized.get("align") or ""
        if not alignment:
            alignment = _extract_alignment(instruction)
        normalized["alignment"] = _extract_alignment(str(alignment))
        return normalized

    if action_type == "set_line_spacing":
        spacing = normalized.get("line_spacing")
        if spacing is None:
            spacing = normalized.get("spacing")
        if spacing is None:
            spacing = _extract_line_spacing(instruction)
        try:
            normalized["line_spacing"] = float(spacing)
        except Exception:
            normalized["line_spacing"] = float(_extract_line_spacing(str(spacing)))
        return normalized

    if action_type == "set_first_line_indent":
        indent = normalized.get("indent_pt")
        if indent is None:
            indent = _extract_first_line_indent_pt(instruction)
        try:
            normalized["indent_pt"] = float(indent)
        except Exception:
            normalized["indent_pt"] = float(_extract_first_line_indent_pt(str(indent)))
        return normalized

    if action_type == "extract_content":
        fields = normalized.get("fields") if isinstance(normalized.get("fields"), list) else []
        if not fields:
            fields = _extract_fields(instruction)
        normalized["fields"] = [str(f).strip() for f in fields if str(f).strip()]
        return normalized

    if action_type == "batch_format":
        is_xlsx_instruction = _looks_like_xlsx_instruction(instruction) or bool(_extract_xlsx_sheet_name(instruction)) or bool(_extract_xlsx_range(instruction))
        if is_xlsx_instruction:
            normalized["font_name"] = str(normalized.get("font_name") or normalized.get("font_family") or _extract_font_name(instruction))
            try:
                normalized["font_size"] = float(normalized.get("font_size") or normalized.get("size_pt") or _extract_xlsx_font_size_pt(instruction))
            except Exception:
                normalized["font_size"] = float(_extract_xlsx_font_size_pt(instruction))
            normalized["horizontal"] = _extract_xlsx_horizontal_alignment(str(normalized.get("horizontal") or instruction))
            normalized["vertical"] = _extract_xlsx_vertical_alignment(str(normalized.get("vertical") or instruction))
            normalized["border_style"] = _extract_xlsx_border_style(str(normalized.get("border_style") or instruction))
            normalized["apply_border"] = _normalize_bool(normalized.get("apply_border"), default=True)
        return normalized

    return normalized


def _normalize_action_target(action_type: str, target: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    normalized = dict(target or {})

    if str(normalized.get("type", "")).strip().lower() == "paragraph" and "paragraph_index" not in normalized:
        normalized["paragraph_index"] = normalized.get("index", -1)

    if "paragraph_index" in normalized:
        try:
            paragraph_index = int(normalized.get("paragraph_index", -1))
        except Exception:
            paragraph_index = -1
        if paragraph_index >= 0:
            normalized["scope"] = normalized.get("scope") or "paragraph"
            normalized["paragraph_index"] = paragraph_index
            normalized["paragraph_index_basis"] = str(normalized.get("paragraph_index_basis", "body") or "body")

    if action_type == "bold_heading":
        normalized.setdefault("scope", "heading")
        try:
            level = int(normalized.get("level"))
        except Exception:
            level = 0
        if level < 1 or level > 6:
            normalized["level"] = _extract_heading_level(instruction)

    if action_type == "set_font_color":
        section_title = str(normalized.get("section_title", "")).strip()
        if not section_title:
            section_title = _extract_section_heading(instruction)
        if section_title:
            normalized["scope"] = "section_content"
            normalized["section_title"] = section_title

    if action_type in {"set_font_family", "set_font_size"}:
        section_title = str(normalized.get("section_title", "")).strip()
        if not section_title:
            section_title = _extract_section_heading(instruction)
        if section_title:
            normalized["scope"] = "section_content"
            normalized["section_title"] = section_title

    if action_type == "set_first_line_indent":
        normalized.setdefault("scope", _extract_text_scope(instruction))

    if action_type in {"batch_format", "auto_column_width", "freeze_header_row", "extract_content", "replace_text", "reorder_paragraphs", "unify_style"}:
        sheet_name = str(normalized.get("sheet", "")).strip()
        if not sheet_name:
            sheet_name = _extract_xlsx_sheet_name(instruction)
        if sheet_name:
            normalized["scope"] = normalized.get("scope") or "worksheet"
            normalized["sheet"] = sheet_name

    if action_type == "batch_format":
        range_ref = str(normalized.get("range", "")).strip()
        if not range_ref:
            range_ref = _extract_xlsx_range(instruction)
        if range_ref:
            normalized["range"] = range_ref

    if action_type == "set_highlight":
        replace_find, replace_target = _extract_replace_pair(instruction)
        if replace_target:
            normalized["find"] = replace_target
        elif replace_find:
            normalized["find"] = replace_find

    return normalized


def _normalize_confidence(value: Any, default: float) -> float:
    try:
        v = float(value)
    except Exception:
        return default
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return v


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _normalize_file_scope(value: Any, instruction: str) -> Literal["md", "xlsx", "docx", "txt", "all"]:
    raw = str(value).strip().lower() if value is not None else ""
    if raw in {"md", "xlsx", "docx", "txt", "all"}:
        return raw  # type: ignore[return-value]
    return _detect_file_scope((instruction or "").lower())


def _manual_confirmation_payload(instruction: str, reason: str) -> Dict[str, Any]:
    return {
        "intent": "extract_content",
        "actions": [
            {
                "action_type": "extract_content",
                "target": {"scope": "document"},
                "params": {
                    "fields": [],
                    "manual_review": True,
                    "reason": reason,
                },
                "confidence": 0.4,
                "requires_confirmation": True,
            }
        ],
        "target": {"scope": "document"},
        "params": {"raw_instruction": instruction},
        "confidence": 0.4,
        "requires_confirmation": True,
        "file_scope": _detect_file_scope((instruction or "").lower()),
    }


def _load_action_plan_schema() -> Dict[str, Any]:
    schema_path = Path(__file__).with_name("action_plan.schema.json")
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_action_plan_schema_text() -> str:
    return json.dumps(_load_action_plan_schema(), ensure_ascii=False)


def _match_by_pattern(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _match_by_keyword_fuzzy(
    text: str,
    keywords: List[str],
    threshold: int = 72,
    action_type: str = "",
) -> bool:
    compact = re.sub(r"\s+", "", text.lower())

    # 防止 "统一样式" 被误识别为批量格式化。
    if action_type == "batch_format" and not re.search(r"批量|一键", compact):
        return False

    for kw in keywords:
        if kw.lower() in compact:
            return True
        score = fuzz.partial_ratio(compact, kw.lower())
        if score >= threshold:
            return True
    return False


def _build_action_payload(action_type: str, text: str, fallback: bool = False, llm_service=None) -> Dict[str, Any]:
    if action_type == "bold_heading":
        return {
            "action_type": action_type,
            "target": {"scope": "heading", "level": _extract_heading_level(text)},
            "params": {"bold": True},
            "confidence": 0.95,
            "requires_confirmation": False,
        }

    if action_type == "insert_page_number":
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {
                "position": "footer",
                "align": "center",
                "per_page": bool(re.search(r"每页|每一页", text)),
            },
            "confidence": 0.95,
            "requires_confirmation": False,
        }

    if action_type == "unify_style":
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {"strategy": "standard", "style_preset": "standard"},
            "confidence": 0.92,
            "requires_confirmation": False,
        }

    if action_type == "reorder_paragraphs":
        src, dst = _extract_reorder_indices(text)
        return {
            "action_type": action_type,
            "target": {"scope": "paragraph"},
            "params": {"from": src, "to": dst, "index_basis": "body_paragraph"},
            "confidence": 0.9,
            "requires_confirmation": True,
        }

    if action_type == "batch_format":
        sheet_name = _extract_xlsx_sheet_name(text)
        range_ref = _extract_xlsx_range(text)
        is_xlsx_instruction = _looks_like_xlsx_instruction(text) or bool(sheet_name) or bool(range_ref)
        params = {
            "apply": "font_size,line_spacing,alignment",
            "scope": "all" if re.search(r"所有|全文|整篇|全篇", text) else "selection",
        }
        if is_xlsx_instruction:
            params.update(
                {
                    "font_name": _extract_font_name(text),
                    "font_size": _extract_xlsx_font_size_pt(text),
                    "horizontal": _extract_xlsx_horizontal_alignment(text),
                    "vertical": _extract_xlsx_vertical_alignment(text),
                    "border_style": _extract_xlsx_border_style(text),
                    "apply_border": True,
                }
            )
        return {
            "action_type": action_type,
            "target": {
                "scope": "worksheet" if is_xlsx_instruction else "selection",
                **({"sheet": sheet_name} if sheet_name else {}),
                **({"range": range_ref} if range_ref else {}),
            },
            "params": params,
            "confidence": 0.88,
            "requires_confirmation": True,
        }

    if action_type == "replace_text":
        find_text, replace_text = _extract_replace_pair(text)
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {
                "find": find_text,
                "replace": replace_text,
                "match_case": False,
            },
            "confidence": 0.9,
            "requires_confirmation": True,
        }

    if action_type == "insert_toc":
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {"position": "beginning"},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "auto_column_width":
        sheet_name = _extract_xlsx_sheet_name(text)
        return {
            "action_type": action_type,
            "target": {"scope": "worksheet", **({"sheet": sheet_name} if sheet_name else {})},
            "params": {"columns": "all"},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "freeze_header_row":
        sheet_name = _extract_xlsx_sheet_name(text)
        return {
            "action_type": action_type,
            "target": {"scope": "worksheet", **({"sheet": sheet_name} if sheet_name else {})},
            "params": {"row": 1},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "clear_document_content":
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {"preserve_structure": True},
            "confidence": 0.93,
            "requires_confirmation": False,
        }

    if action_type == "remove_blank_lines":
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {"trim_whitespace": True},
            "confidence": 0.88,
            "requires_confirmation": False,
        }

    if action_type == "set_font_family":
        target = _extract_formatting_target(text, llm_service)
        return {
            "action_type": action_type,
            "target": target,
            "params": {"font_name": _extract_font_name(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_font_color":
        target = _extract_formatting_target(text, llm_service)
        return {
            "action_type": action_type,
            "target": target,
            "params": {"color": _extract_font_color(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_font_size":
        target = _extract_formatting_target(text, llm_service)
        return {
            "action_type": action_type,
            "target": target,
            "params": {"size_pt": _extract_font_size_pt(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_paragraph_alignment":
        return {
            "action_type": action_type,
            "target": {"scope": _extract_text_scope(text)},
            "params": {"alignment": _extract_alignment(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_line_spacing":
        return {
            "action_type": action_type,
            "target": {"scope": _extract_text_scope(text)},
            "params": {"line_spacing": _extract_line_spacing(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_first_line_indent":
        return {
            "action_type": action_type,
            "target": {"scope": _extract_text_scope(text)},
            "params": {"indent_pt": _extract_first_line_indent_pt(text)},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_highlight":
        # 优先高亮替换后的目标文本；若无替换对，再从高亮语句中抽取。
        find_text = ""
        replace_find, replace_target = _extract_replace_pair(text)
        if replace_target:
            find_text = replace_target
        elif replace_find:
            find_text = replace_find
        else:
            quoted = re.findall(r"[“\"']([^”\"']+)[”\"']", text)
            if quoted:
                find_text = quoted[0].strip()
            m = re.search(r"(?:高亮|标记)[\s\"'“”]*(.+?)(?:[，。；;\n]|\s+$)", text)
            if m and not find_text:
                find_text = m.group(1).strip().strip("\"'“”")
        
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {
                "find": find_text,
                "highlight_color": "yellow",
            },
            "confidence": 0.85,
            "requires_confirmation": True,
        }

    if action_type == "insert_table":
        rows, cols = _extract_table_dimensions(text)
        return {
            "action_type": action_type,
            "target": {"scope": "document", "position": "end"},
            "params": {
                "rows": rows,
                "cols": cols,
                "bold_header": True if "表头加粗" in text or "表头" in text else False,
            },
            "confidence": 0.88,
            "requires_confirmation": True,
        }

    if action_type == "insert_footer_text":
        footer_text = _extract_footer_text(text)
        preserve_existing_page = bool(re.search(r"保留(?:已有)?页码|不覆盖(?:已有)?页码|追加", text))
        include_page_number = bool(re.search(r"(?:插入|添加|显示|包含).{0,4}页码|带页码", text)) and not preserve_existing_page
        return {
            "action_type": action_type,
            "target": {"scope": "document", "position": "footer"},
            "params": {
                "text": footer_text,
                "alignment": "center" if "居中" in text else "left",
                "include_page_number": include_page_number,
                "preserve_existing_page_number": preserve_existing_page,
            },
            "confidence": 0.85,
            "requires_confirmation": True,
        }

    if action_type == "set_heading_numbering":
        level = _extract_heading_level(text)
        return {
            "action_type": action_type,
            "target": {"scope": "document", "level": level},
            "params": {
                "format": _extract_numbering_format(text),
            },
            "confidence": 0.85,
            "requires_confirmation": False,
        }

    if action_type == "set_italic":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"italic": True},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_underline":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"underline": True},
            "confidence": 0.9,
            "requires_confirmation": False,
        }

    if action_type == "set_paragraph_spacing":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {
                "before_spacing": _extract_paragraph_spacing(text, "before"),
                "after_spacing": _extract_paragraph_spacing(text, "after"),
            },
            "confidence": 0.85,
            "requires_confirmation": False,
        }

    if action_type == "set_bullet_list":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"bullet_type": "bullet"},
            "confidence": 0.85,
            "requires_confirmation": True,
        }

    if action_type == "set_numbered_list":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"number_format": "decimal"},
            "confidence": 0.85,
            "requires_confirmation": True,
        }

    if action_type == "set_paragraph_shading":
        shading_color = _extract_shading_color(text)
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"shading_color": shading_color},
            "confidence": 0.8,
            "requires_confirmation": True,
        }

    if action_type == "set_paragraph_border":
        return {
            "action_type": action_type,
            "target": _extract_formatting_target(text, llm_service),
            "params": {"border_type": "all"},
            "confidence": 0.8,
            "requires_confirmation": True,
        }

    if action_type == "add_hyperlink":
        url, link_text = _extract_hyperlink_info(text)
        return {
            "action_type": action_type,
            "target": {"scope": "document"},
            "params": {
                "url": url,
                "display_text": link_text,
            },
            "confidence": 0.85,
            "requires_confirmation": True,
        }

    return {
        "action_type": "extract_content",
        "target": {"scope": "document"},
        "params": {"fields": _extract_fields(text)},
        "confidence": 0.7 if fallback else 0.92,
        "requires_confirmation": False,
    }


def _build_bold_heading_actions(text: str) -> List[Dict[str, Any]]:
    levels = _extract_heading_levels(text)
    actions: List[Dict[str, Any]] = []
    for lv in levels:
        actions.append(
            {
                "action_type": "bold_heading",
                "target": {"scope": "heading", "level": lv},
                "params": {"bold": True},
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        )
    return actions


def _expand_bold_heading_levels(actions: List[Dict[str, Any]], instruction: str) -> List[Dict[str, Any]]:
    levels = _extract_heading_levels(instruction)
    if len(levels) <= 1:
        return actions

    normalized_actions: List[Dict[str, Any]] = []
    existing_levels = set()
    has_bold_heading = False

    for action in actions:
        if action.get("action_type") != "bold_heading":
            normalized_actions.append(action)
            continue

        has_bold_heading = True
        target = action.get("target") if isinstance(action.get("target"), dict) else {}
        try:
            lv = int(target.get("level", 0))
        except Exception:
            lv = 0
        if lv > 0:
            existing_levels.add(lv)
            normalized_actions.append(action)

    if not has_bold_heading:
        return actions

    for lv in levels:
        if lv in existing_levels:
            continue
        normalized_actions.append(
            {
                "action_type": "bold_heading",
                "target": {"scope": "heading", "level": lv},
                "params": {"bold": True},
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        )

    return normalized_actions


def _extract_heading_level(text: str) -> int:
    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

    m_digit = re.search(r"([1-6])级标题", text)
    if m_digit:
        return int(m_digit.group(1))

    m_cn = re.search(r"([一二三四五六])级标题", text)
    if m_cn:
        return cn_map[m_cn.group(1)]

    m_h = re.search(r"h([1-6])", text, flags=re.IGNORECASE)
    if m_h:
        return int(m_h.group(1))

    return 1


def _extract_heading_levels(text: str) -> List[int]:
    levels: List[int] = []
    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

    # 覆盖“一级和二级标题”“一级、二级标题”等并列写法。
    for m in re.finditer(r"([一二三四五六1-6])级", text):
        raw = m.group(1)
        if raw.isdigit():
            levels.append(int(raw))
        else:
            levels.append(cn_map[raw])

    for m in re.finditer(r"([1-6])级标题", text):
        levels.append(int(m.group(1)))

    for m in re.finditer(r"([一二三四五六])级标题", text):
        levels.append(cn_map[m.group(1)])

    for m in re.finditer(r"h([1-6])", text, flags=re.IGNORECASE):
        levels.append(int(m.group(1)))

    unique_levels = sorted({lv for lv in levels if 1 <= lv <= 6})
    if unique_levels:
        return unique_levels
    return [_extract_heading_level(text)]


def _extract_reorder_indices(text: str) -> tuple[int, int]:
    def _parse_zh_num(raw: str) -> int:
        s = (raw or "").strip()
        if not s:
            return 0
        if s.isdigit():
            return int(s)
        zh_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if s in zh_map:
            return zh_map[s]
        if s.startswith("十") and len(s) == 2 and s[1] in zh_map:
            return 10 + zh_map[s[1]]
        if len(s) == 2 and s[0] in zh_map and s[1] == "十":
            return zh_map[s[0]] * 10
        if len(s) == 3 and s[0] in zh_map and s[1] == "十" and s[2] in zh_map:
            return zh_map[s[0]] * 10 + zh_map[s[2]]
        return 0

    unit = r"(?:段|行)"

    patterns = [
        rf"从第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:移动|挪到|放到|调到|到|移到)第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:之后)?",
        rf"把第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:移动|挪到|放到|调到|到|移到)第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:之后)?",
        rf"将第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:移动|挪到|放到|调到|到|移到)第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:之后)?",
        rf"第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:移动|挪到|放到|调到|到|移到).{{0,8}}第\s*([一二三四五六七八九十\d]+)\s*{unit}(?:之后)?",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            src = _parse_zh_num(m.group(1))
            dst = _parse_zh_num(m.group(2))
            if src > 0 and dst > 0:
                return src, dst
    return 0, 0


def _extract_fields(text: str) -> List[str]:
    m = re.search(r"(?:提取|抽取|捞出来|捞出)(.+)", text)
    if not m:
        m = re.search(r"(?:结构化结果.{0,10}[：:])(.+)", text)
    if not m:
        m = re.search(r"(?:给我[：:])(.+)", text)
    if not m:
        return []
    raw = m.group(1).strip(" ：:。；;，,")
    if not raw:
        return []

    # 若前半段是口语引导词，优先取冒号后的字段列表。
    if "：" in raw:
        raw = raw.split("：")[-1].strip()
    if ":" in raw:
        raw = raw.split(":")[-1].strip()

    raw = re.sub(r"^(?:做|进行)?结构化(?:结果|输出)?(?:给我|返回)?", "", raw).strip(" ：:")

    fields = re.split(r"[、,，和及与\s]+", raw)
    cleaned: List[str] = []
    for f in fields:
        item = (f or "").strip().strip("\"'“”‘’")
        item = re.sub(r"(?:三个字段|两个字段|字段).*$", "", item)
        item = item.strip().strip("\"'“”‘’")
        if not item:
            continue
        if item in {"文档", "内容", "中的", "里", "为", "并返回结构化结果", "返回结构化结果"}:
            continue
        cleaned.append(item)
    return cleaned


def _looks_like_xlsx_instruction(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(
        re.search(r"[A-Za-z]+\d+\s*[:：]\s*[A-Za-z]+\d+", text)
        or re.search(r"工作表|表格|单元格|列宽|行高|冻结首行|冻结表头|自动列宽", text)
        or "xlsx" in lowered
        or "excel" in lowered
    )


def _extract_xlsx_sheet_name(text: str) -> str:
    patterns = [
        r"工作表[“\"']([^”\"']+)[”\"']",
        r"表[“\"']([^”\"']+)[”\"']",
        r"sheet\s*[“\"']?([^”\"'\s，。；;]+)[”\"']?",
        r"工作表\s*([^，。；;:：\n]{1,20})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            name = match.group(1).strip().strip("“”'\"")
            if name:
                return name
    return ""


def _extract_xlsx_range(text: str) -> str:
    match = re.search(r"([A-Za-z]+\d+)\s*[:：]\s*([A-Za-z]+\d+)", text)
    if match:
        return f"{match.group(1).upper()}:{match.group(2).upper()}"
    return ""


def _extract_xlsx_font_size_pt(text: str) -> float:
    named = {
        "小四": 12.0,
        "四号": 14.0,
        "五号": 10.5,
        "小五": 9.0,
    }
    for k, v in named.items():
        if k in text:
            return v

    match = re.search(r"(?:字号|字体大小|字体设为|font\s*size|size)\s*[:：=]?\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))

    return 11.0


def _extract_xlsx_horizontal_alignment(text: str) -> str:
    lowered = text.lower()
    if "水平居中" in text or "水平置中" in text or "居中" in text or "center" in lowered or "居中对齐" in text:
        return "center"
    if "水平左" in text or "左对齐" in text or "left" in lowered:
        return "left"
    if "水平右" in text or "右对齐" in text or "right" in lowered:
        return "right"
    if "两端对齐" in text or "justify" in lowered:
        return "justify"
    return "center"


def _extract_xlsx_vertical_alignment(text: str) -> str:
    lowered = text.lower()
    if "垂直居中" in text or "上下居中" in text or "middle" in lowered or "center" in lowered:
        return "center"
    if "顶端" in text or "顶部" in text or "top" in lowered:
        return "top"
    if "底端" in text or "底部" in text or "bottom" in lowered:
        return "bottom"
    return "center"


def _extract_xlsx_border_style(text: str) -> str:
    lowered = text.lower()
    if "粗边框" in text or "thick" in lowered:
        return "thick"
    if "中边框" in text or "medium" in lowered:
        return "medium"
    if "细边框" in text or "thin" in lowered or "细框" in text:
        return "thin"
    return "thin"


def _extract_replace_pair(text: str) -> tuple[str, str]:
    # 优先使用引号包裹内容，避免复合指令把后续子句吞进替换文本。
    quoted_patterns = [
        r"(?:将|把)[^“\"']*[“\"'](.+?)[”\"'][^，。,；;\n]*替换为\s*[“\"'](.+?)[”\"']",
        r"查找\s*[“\"'](.+?)[”\"']\s*替换\s*[“\"'](.+?)[”\"']",
        r"(?:把)?\s*[“\"'](.+?)[”\"']\s*改成\s*[“\"'](.+?)[”\"']",
    ]
    for p in quoted_patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip(), m.group(2).strip()

    # 非引号场景：替换后的文本只截取到首个分隔符（逗号、分号、句号、换行）。
    patterns = [
        r"(?:将|把)\s*([^，。,；;\n]+?)\s*替换为\s*([^，。,；;\n]+)",
        r"(?:将|把)\s*([^，。,；;\n]+?)\s*(?:统一)?换成\s*([^，。,；;\n]+)",
        r"(?:将|把)\s*([^，。,；;\n]+?)\s*改为\s*([^，。,；;\n]+)",
        r"查找\s*([^，。,；;\n]+?)\s*替换\s*([^，。,；;\n]+)",
        r"(?:把)?\s*([^，。,；;\n]+?)\s*改成\s*([^，。,；;\n]+)",
        r"(?:把)?\s*([^，。,；;\n]+?)\s*改为\s*([^，。,；;\n]+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            find_text = m.group(1).strip().strip("\"'“”")
            replace_text = m.group(2).strip().strip("\"'“”")
            find_text = re.sub(r"^(?:文里(?:出现的)?|文中(?:出现的)?|文内(?:出现的)?|出现的)", "", find_text).strip("\"'“”")
            return find_text, replace_text
    return "", ""


def _split_instruction_segments(text: str) -> List[str]:
    if not text:
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # 先尝试解析“单行编号列表”（例如：1. ... 2. ... 3. ...），
    # 前端聊天输入常见这种形态，若不拆分会导致多个动作共用整段上下文而串扰。
    marker = r"(?:\d+\.(?!\d)|\d+[、）)]|[一二三四五六七八九十]+[\.、）)])"
    inline_pattern = rf"(?:^|\s)({marker})\s*(.+?)(?=(?:\s+{marker}\s*)|$)"
    inline_items = [m.group(2).strip(" \t\n；;。") for m in re.finditer(inline_pattern, normalized)]
    if len(inline_items) >= 2:
        return inline_items

    # 优先按编号列表拆分（如 1. / 2、 / 3）），每一条通常对应一个动作。
    numbered_split = re.split(r"(?:^|\n)\s*(?:\d+|[一二三四五六七八九十]+)\s*[\.、）)]\s*", normalized)
    numbered_items = [item.strip(" \t\n；;。") for item in numbered_split if item.strip(" \t\n；;。")]
    if len(numbered_items) >= 2:
        return numbered_items

    # 其次按换行切分（很多 prompt 是逐行动作）。
    line_items = [line.strip(" \t；;。") for line in normalized.split("\n") if line.strip(" \t；;。")]
    if len(line_items) >= 2:
        return line_items

    # 回退：按强分隔符切，再按连接词切，避免整句污染作用域。
    primary = [s.strip() for s in re.split(r"[；;。]\s*", normalized) if s.strip()]
    segments: List[str] = []
    for part in primary:
        sub_parts = [
            s.strip()
            for s in re.split(r"[，,]\s*(?=再|并|最后|然后|在文档|把正文|将文中|再把|并在|并把|并将|并给|并对|并把)", part)
            if s.strip()
        ]
        if sub_parts:
            segments.extend(sub_parts)
        else:
            segments.append(part)

    return segments or [normalized]


def _find_action_contexts(action_type: str, rule: Dict[str, Any], segments: List[str]) -> List[str]:
    contexts: List[str] = []
    for seg in segments:
        if _segment_matches_action(action_type, rule, seg):
            contexts.append(seg)

    return contexts


def _segment_matches_action(action_type: str, rule: Dict[str, Any], seg: str) -> bool:
    if action_type == "replace_text":
        if _is_standalone_output_rename(seg):
            return False
        if re.search(r"替换|查找", seg):
            return True
        if re.search(r"(?:将|把)\s*.+?\s*改为\s*.+", seg):
            return True
        if re.search(r".+?\s*改成\s*.+", seg):
            return True
        return False

    if action_type == "remove_blank_lines":
        # 「删除文件中的内容」不是删空行
        if re.search(r"(?:删除|去掉|清理|清除|清空)", seg) and re.search(r"内容", seg) and not re.search(r"空行", seg):
            return False

    if action_type == "insert_footer_text":
        # 纯页码+对齐语义由 insert_page_number 负责，避免把提示词文本写进页脚。
        has_quoted_text = bool(re.search(r"[\"'“”][^\"'“”]+[\"'“”]", seg))
        if re.search(r"页脚", seg) and re.search(r"页码", seg) and not has_quoted_text:
            if re.search(r"居中|左对齐|右对齐|显示|插入页码|添加页码", seg) and not re.search(r"追加|附加|文本|内容|写入", seg):
                return False

    if action_type == "set_font_family" and re.search(r"(?:颜色|色彩|颜色词|字体颜色|文字颜色|紫色|紫|红色|蓝色|黑色|绿色|字号|字大小|字体大小)", seg):
        # 避免“字体颜色/字号”把字体族动作误触发。
        if not re.search(r"宋体|黑体|楷体|仿宋|微软雅黑|Times New Roman|Arial|Calibri", seg, flags=re.IGNORECASE):
            return False

    if action_type == "set_paragraph_alignment" and re.search(r"页脚|页眉|页码", seg):
        # 避免“页脚居中插入页码”触发正文/全局段落对齐动作。
        return False

    if action_type == "set_bullet_list" and re.search(r"编号|有序|numbered|numbering", seg, flags=re.IGNORECASE):
        # 避免编号列表语句被误识别为项目符号列表。
        return False

    if action_type == "set_numbered_list" and re.search(r"项目符号|无序|bullet", seg, flags=re.IGNORECASE):
        # 避免项目符号语句被误识别为编号列表。
        return False

    return _match_by_pattern(seg, rule["patterns"]) or _match_by_keyword_fuzzy(
        seg,
        rule["keywords"],
        action_type=action_type,
    )


def _deduplicate_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for action in actions:
        key = json.dumps(
            {
                "action_type": action.get("action_type"),
                "target": action.get("target", {}),
                "params": action.get("params", {}),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _post_process_actions(actions: List[Dict[str, Any]], instruction: str) -> List[Dict[str, Any]]:
    if not actions:
        return actions

    for action in actions:
        action_type = action.get("action_type")
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        target = action.get("target") if isinstance(action.get("target"), dict) else {}
        segment_text = str(params.get("__segment_text") or instruction)

        def _set_body_paragraph_index(idx: int) -> None:
            target["scope"] = "paragraph"
            target["paragraph_index"] = idx
            target["paragraph_index_basis"] = "body"
            action["target"] = target

        if action_type == "set_font_family":
            if params.get("italic"):
                action["action_type"] = "set_italic"
                action["params"] = {"italic": True}
                continue
            if params.get("underline"):
                action["action_type"] = "set_underline"
                action["params"] = {"underline": True}
                continue

        if action_type == "set_paragraph_alignment":
            if params.get("border") or str(params.get("border_type", "")).strip().lower() in {"all", "paragraph"}:
                action["action_type"] = "set_paragraph_border"
                action["params"] = {"border_type": "all"}
                continue
            if params.get("background_color") or params.get("shading_color"):
                action["action_type"] = "set_paragraph_shading"
                shading_color = params.get("shading_color") or params.get("background_color") or _extract_shading_color(instruction)
                action["params"] = {"shading_color": _extract_shading_color(str(shading_color))}
                continue

        if action_type == "set_highlight":
            target_text = str(target.get("text") or target.get("target_text") or "").strip()
            if target_text:
                params["find"] = target_text
                action["params"] = params

        if action_type == "reorder_paragraphs":
            source_index = target.get("paragraph_index")
            new_index = params.get("new_index")
            from_idx = params.get("from")
            to_idx = params.get("to")
            if (not from_idx or int(from_idx) <= 0) and source_index is not None:
                try:
                    params["from"] = int(source_index) + 1
                except Exception:
                    pass
            if (not to_idx or int(to_idx) <= 0) and new_index is not None:
                try:
                    params["to"] = int(new_index)
                except Exception:
                    pass
            action["params"] = params

        if action_type in {"set_italic", "set_underline", "set_paragraph_border", "set_paragraph_shading"}:
            explicit_idx = _extract_explicit_paragraph_index(segment_text)
            if explicit_idx >= 0:
                _set_body_paragraph_index(explicit_idx)

    for action in actions:
        if action.get("action_type") != "set_font_family":
            continue
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        segment_text = str(params.get("__segment_text") or instruction)
        color_cue = re.search(r"(?:颜色|色彩|红色|蓝色|黑色|绿色|紫色|紫|orange|yellow|purple|violet)", segment_text, re.IGNORECASE)
        explicit_font_cue = re.search(r"宋体|黑体|楷体|仿宋|微软雅黑|Times New Roman|Arial|Calibri", segment_text, re.IGNORECASE)
        if color_cue and not explicit_font_cue:
            action["action_type"] = "set_font_color"
            params["color"] = _extract_font_color(segment_text)
            action["params"] = params

    replace_targets = [
        str((a.get("params") or {}).get("replace", "")).strip()
        for a in actions
        if a.get("action_type") == "replace_text"
    ]
    replace_target = next((t for t in replace_targets if t), "")
    if replace_target:
        for action in actions:
            if action.get("action_type") != "set_highlight":
                continue
            params = action.get("params") if isinstance(action.get("params"), dict) else {}
            find_text = str(params.get("find", "")).strip()
            if not find_text or find_text in {"标记修改处", "修改处", "高亮", "标记"}:
                params["find"] = replace_target
                action["params"] = params

    has_page_number = any(a.get("action_type") == "insert_page_number" for a in actions)
    if not has_page_number:
        return actions

    filtered: List[Dict[str, Any]] = []
    for action in actions:
        if action.get("action_type") != "set_paragraph_alignment":
            filtered.append(action)
            continue

        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        target = action.get("target") if isinstance(action.get("target"), dict) else {}
        alignment = str(params.get("alignment", "")).lower()
        scope = str(target.get("scope", "")).lower()
        segment_text = str(params.get("__segment_text") or instruction)

        # "页脚居中插入页码" 不应生成正文/全局段落居中动作。
        if alignment == "center" and scope in {"all", "document", "paragraph"} and re.search(r"页脚|页码", segment_text):
            continue

        filtered.append(action)

    return filtered


def _detect_file_scope(lowered: str) -> Literal["md", "xlsx", "docx", "txt", "all"]:
    for scope, keywords in _FILE_SCOPE_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return scope
    return "all"


def _extract_text_scope(text: str) -> str:
    lowered = text.lower()
    if _extract_section_heading(text):
        return "section_content"
    if "标题" in text or "heading" in lowered:
        return "heading"
    if "正文" in text or "body" in lowered:
        return "body"
    return "all"


def _extract_section_heading(text: str) -> str:
    m = re.search(r"[“\"']([^”\"']+)[”\"']\s*(?:题目|标题|章节).{0,8}(?:下|下面)", text)
    if m:
        return m.group(1).strip()

    m = re.search(r"(?:所有)?([\u4e00-\u9fffA-Za-z0-9]+)\s*(?:题目|标题|章节).{0,8}(?:下|下面)", text)
    if m:
        return m.group(1).strip()

    if "综合" in text and "内容" in text:
        return "综合"
    return ""


def _extract_font_name(text: str) -> str:
    candidates = ["宋体", "黑体", "楷体", "仿宋", "微软雅黑", "Times New Roman", "Arial", "Calibri"]
    lowered = text.lower()
    for c in candidates:
        if c.lower() in lowered:
            return c
    return "宋体"


def _extract_font_color(text: str) -> str:
    color_map = {
        "红": "FF0000",
        "红色": "FF0000",
        "red": "FF0000",
        "蓝": "0000FF",
        "蓝色": "0000FF",
        "blue": "0000FF",
        "紫": "800080",
        "紫色": "800080",
        "purple": "800080",
        "violet": "8A2BE2",
        "黑": "000000",
        "黑色": "000000",
        "black": "000000",
        "绿": "008000",
        "绿色": "008000",
        "green": "008000",
        "灰": "808080",
        "灰色": "808080",
        "gray": "808080",
        "grey": "808080",
        "橙": "FFA500",
        "橙色": "FFA500",
        "orange": "FFA500",
    }
    m_hex = re.search(r"#?([0-9a-fA-F]{6})", text)
    if m_hex:
        return m_hex.group(1).upper()
    for k, v in color_map.items():
        if k in text:
            return v
    return "000000"


def _extract_font_size_pt(text: str) -> float:
    named = {
        "小四": 12.0,
        "四号": 14.0,
        "五号": 10.5,
        "小五": 9.0,
    }
    for k, v in named.items():
        if k in text:
            return v

    # 仅在"字号/字体"上下文中提取磅值，避免把"段前6磅/段后12磅"误判为字号。
    m_pt = re.search(r"(?:字号|字体|字体大小|字大小).{0,4}(\d+(?:\.\d+)?)\s*磅", text)
    if m_pt:
        return float(m_pt.group(1))

    m_num = re.search(r"(?:字号|字体大小|字大小).{0,4}(\d+(?:\.\d+)?)", text)
    if m_num:
        return float(m_num.group(1))
    return 11.0


def _extract_alignment(text: str) -> str:
    if "两端" in text or "justify" in text.lower():
        return "justify"
    if "右对齐" in text or "right" in text.lower():
        return "right"
    if "居中" in text or "center" in text.lower() or "置中" in text:
        return "center"
    return "left"


def _extract_line_spacing(text: str) -> float:
    if "双倍" in text or "2倍" in text:
        return 2.0
    if "1.5" in text or "一倍半" in text:
        return 1.5
    if "单倍" in text or "1倍" in text:
        return 1.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*倍", text)
    if m:
        return float(m.group(1))
    return 1.5


def _extract_first_line_indent_pt(text: str) -> float:
    # 默认 2 字符（约 24pt，按 12pt 正文基准）。
    if re.search(r"首行空两格|2\s*字符|两字符|两个字符", text):
        return 24.0

    m_char = re.search(r"首行缩进\s*(\d+(?:\.\d+)?)\s*字符", text)
    if m_char:
        return float(m_char.group(1)) * 12.0

    m_pt = re.search(r"首行缩进\s*(\d+(?:\.\d+)?)\s*磅", text)
    if m_pt:
        return float(m_pt.group(1))

    return 24.0


def _extract_table_dimensions(text: str) -> tuple[int, int]:
    """提取表格行数和列数，默认 3 行 4 列"""
    # 匹配 "3行4列"、"3x4"、"3X4" 等格式
    m = re.search(r"(\d+)\s*(?:行|x|X|×)\s*(\d+)\s*(?:列)?", text)
    if m:
        rows = int(m.group(1))
        cols = int(m.group(2))
        if rows > 0 and cols > 0:
            return rows, cols
    
    return 3, 4  # 默认 3 行 4 列


def _extract_footer_text(text: str) -> str:
    """提取页脚文本内容"""
    preserve_existing_page = bool(re.search(r"保留(?:已有)?页码|不覆盖(?:已有)?页码|追加", text))

    # 优先查找引号内的文本
    m = re.search(r'["\'“”](.+?)["\'“”]', text)
    if m:
        quoted = m.group(1).strip()
        normalized = quoted.replace("page_count", "{total_pages}")
        if re.search(r"共\s*[Xx]\s*页", normalized):
            normalized = re.sub(r"X|x", "{total_pages}", normalized, count=1)
        if re.search(r"第\s*[Xx]\s*页", normalized):
            normalized = re.sub(r"X|x", "{page_number}", normalized, count=1)
        if "页码" in text and "页脚" in text and "{page_number}" not in normalized and not preserve_existing_page:
            normalized = f"第{{page_number}}页，{normalized}" if normalized else "第{page_number}页"
        return normalized
    
    # 查找"页脚"后跟"插入"等动词的文本
    m = re.search(r"(?:在)?页脚[\s]*(?:插入|添加|写入|追加|附加)[\s]*[\"'“”]?([^\n，。、；;]+)[\"'“”]?", text)
    if m:
        extracted = m.group(1).strip()
        if re.search(r"^页码(?:并|且)?(?:居中|左对齐|右对齐|显示)?$", extracted):
            extracted = ""
        if extracted:
            return extracted
    
    # 查找"共X页"格式
    if "共" in text and "页" in text:
        if "页码" in text:
            return "第{page_number}页，共{total_pages}页"
        return "共{total_pages}页"

    if "page_count" in text.lower():
        return "共{total_pages}页"
    
    # 查找包含页码的指令
    if "页码" in text and "页脚" in text and not preserve_existing_page:
        return "第{page_number}页"
    
    return "Page {page_number}"


def _extract_numbering_format(text: str) -> str:
    """提取标题编号格式"""
    # 查找"第X章"格式
    if "第" in text and "章" in text:
        return "第{index}章"
    # 查找"X."格式
    if re.search(r"\d+\.|第\d+[、,]", text):
        return "第{index}."
    # 默认格式
    return "第{index}章"


def _extract_paragraph_spacing(text: str, position: str = "after") -> float:
    """提取段落间距（单位：磅）"""
    # 匹配 "12磅"、"0.5行" 等格式
    if position == "before":
        m = re.search(r"(?:段前|前)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:磅|pt|行)", text)
    else:
        m = re.search(r"(?:段后|后)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:磅|pt|行)", text)
    
    if m:
        return float(m.group(1))
    
    # 默认值
    return 6.0 if position == "after" else 0.0


def _extract_shading_color(text: str) -> str:
    """提取段落底纹颜色"""
    color_map = {
        "黄": "FFFF00",
        "黄色": "FFFF00",
        "灰": "D3D3D3",
        "灰色": "D3D3D3",
        "蓝": "ADD8E6",
        "蓝色": "ADD8E6",
        "紫": "D8BFD8",
        "紫色": "D8BFD8",
        "purple": "D8BFD8",
        "绿": "90EE90",
        "绿色": "90EE90",
        "红": "FFB6C1",
        "红色": "FFB6C1",
        "pink": "FFB6C1",
    }
    
    for key, value in color_map.items():
        if key in text:
            return value
    
    # 尝试从文本中提取十六进制颜色
    m = re.search(r"#?([0-9a-fA-F]{6})", text)
    if m:
        return m.group(1).upper()
    
    return "FFFF00"  # 默认黄色


def _extract_hyperlink_info(text: str) -> tuple[str, str]:
    """提取超链接URL和显示文本"""
    # 匹配多种格式：
    # 1. "链接到https://example.com"
    # 2. "指向https://example.com"  
    # 3. "https://example.com"
    m = re.search(r"(?:链接|超链接|指向)?.*?(https?://[^\s\'\"）\)]+)", text)
    url = m.group(1) if m else ""
    
    # 查找显示文本 - 查找 "文本为'...'\" 或 "显示为'...'" 格式
    # 优先查找双引号或提供明确的文本
    m = re.search(r"(?:文本|显示文本|显示为|display|text)\s*[为是]?\s*[\"\'\'']?([^\"\'\'\)\]]+)[\"\'\'']?", text)
    if m:
        display_text = m.group(1).strip()
        # 移除尾部的中文符号
        display_text = re.sub(r'[，、，。；：].*$', '', display_text)
    else:
        display_text = ""
    
    return url, display_text


def _extract_formatting_target(text: str, llm_service=None) -> Dict[str, Any]:
    """
    从格式化指令中提取目标文本和段落信息。
    优先使用 LLM 提取，规则作为兜底。
    
    支持以下格式：
    - "在第一段的'xxx'应用斜体"
    - "'xxx'应用斜体"
    - "将'xxx'改为斜体"
    - "把'2021年'改成字体15磅"（规则无法识别→LLM理解）
    
    返回示例：
    - {'paragraph_index': 0, 'target_text': 'xxx', 'scope': 'selective'}
    - {'scope': 'paragraph', 'paragraph_index': 2}
    - {'scope': 'document'} 如果无法提取
    """
    def _extract_explicit_target_text(raw_text: str) -> str:
        target_texts: List[str] = []
        for pattern in [r"'([^']+)'", r'"([^"]+)"']:
            for m in re.finditer(pattern, raw_text):
                if m.lastindex and m.group(1):
                    target_texts.append(m.group(1).strip())
        return target_texts[0] if target_texts else ""

    explicit_paragraph_index = _extract_explicit_paragraph_index(text)
    explicit_target_text = _extract_explicit_target_text(text)

    def _rule_fallback() -> Dict[str, Any]:
        paragraph_index = explicit_paragraph_index
        target_text = explicit_target_text

        if target_text:
            result = {
                "scope": "selective",
                "target_text": target_text,
                "paragraph_index": paragraph_index,
            }
            if paragraph_index >= 0:
                result["paragraph_index_basis"] = "body"
            return result

        if paragraph_index >= 0:
            return {
                "scope": "paragraph",
                "paragraph_index": paragraph_index,
                "paragraph_index_basis": "body",
            }

        scope = _extract_text_scope(text)
        if scope == "all":
            return {"scope": "document"}
        return {"scope": scope}

    # ========== 阶段1：LLM 优先 ==========
    try:
        if llm_service is None:
            llm_service = get_llm_service()
        if hasattr(llm_service, "is_available") and not llm_service.is_available():
            return _rule_fallback()
        
        # 构造 LLM 提示词，让它识别：
        # 1. 是否有明确的段落位置指示
        # 2. 是否有明确的目标文本
        # 3. 如果都没有，应该应用到整个文档还是某个段落
        system_prompt = """你是一个文档编辑指令理解专家。分析用户的格式化指令，识别出：
    1. 目标段落位置（第几段，如"第一段"、"第二段"，用数字回答，如 1, 2；-1表示未指定）。
       "第X段"默认为正文段落序号（排除标题、署名、日期等元信息行）
2. 要格式化的具体文本内容（用'XXX'表示，如果没有明确指定则回答'ALL'）
3. 如果都没有明确指定，应用范围是整个文档('document')还是第一段('paragraph')

严格按照以下JSON格式回答（只返回JSON，不包含其他说明）：
    {"paragraph_index": <数字>, "paragraph_index_basis": "<body|absolute>", "target_text": "<文本或ALL>", "scope": "<selective|paragraph|document>"}

注意：
- paragraph_index: -1 表示未指定，0表示第一段，1表示第二段
    - paragraph_index_basis: 默认 body
- target_text: 同一行或同一段落中的关键词，'ALL' 表示整个段落或文档
- scope: selective(精确文本), paragraph(整段), document(全文)
- 若用户明确指定“第X段”或引号内目标词，禁止输出 document，必须保留该约束。"""
        
        user_input = f"分析这个指令：{text}"
        
        response = llm_service.chat_with_system(system_prompt, user_input)
        
        # 尝试从 LLM 响应中提取 JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                import json
                result_dict = json.loads(json_match.group())
                
                # 验证并规范化 LLM 的输出
                paragraph_index = result_dict.get("paragraph_index", -1)
                paragraph_index_basis = str(
                    result_dict.get("paragraph_index_basis", result_dict.get("paragraphindexbasis", "body")) or "body"
                ).lower()
                target_text = result_dict.get("target_text", "")
                scope = result_dict.get("scope", "document")
                
                # 构造返回值
                llm_result: Dict[str, Any] = {}
                
                if target_text and target_text != "ALL" and paragraph_index >= 0:
                    # 有明确的文本和段落位置
                    llm_result = {
                        "scope": "selective",
                        "target_text": target_text,
                        "paragraph_index": paragraph_index,
                        "paragraph_index_basis": paragraph_index_basis if paragraph_index_basis in {"body", "absolute"} else "body",
                    }
                elif target_text and target_text != "ALL":
                    # 只有文本，没有明确段落位置
                    llm_result = {
                        "scope": "selective",
                        "target_text": target_text,
                        "paragraph_index": -1,
                    }
                elif paragraph_index >= 0:
                    # 只有段落位置，没有明确文本
                    llm_result = {
                        "scope": "paragraph",
                        "paragraph_index": paragraph_index,
                        "paragraph_index_basis": paragraph_index_basis if paragraph_index_basis in {"body", "absolute"} else "body",
                    }
                else:
                    # 都没有明确指定，返回 LLM 建议的范围
                    if scope == "paragraph":
                        llm_result = {"scope": "paragraph", "paragraph_index": 0}
                    else:
                        llm_result = {"scope": "document"}

                # 显式约束优先：若用户写了“第X段/引号文本”，用规则抽取结果覆盖 LLM 偏移。
                if explicit_target_text:
                    llm_result["scope"] = "selective"
                    llm_result["target_text"] = explicit_target_text

                if explicit_paragraph_index >= 0:
                    llm_result["paragraph_index"] = explicit_paragraph_index
                    llm_result["paragraph_index_basis"] = "body"
                    if llm_result.get("scope") == "document":
                        llm_result["scope"] = "selective" if llm_result.get("target_text") else "paragraph"

                # 指令里有明确目标线索时，不接受 LLM 的 document 级泛化，回退规则提取。
                has_explicit_cues = bool(
                    explicit_paragraph_index >= 0 or bool(explicit_target_text)
                )
                if has_explicit_cues and llm_result.get("scope") == "document":
                    return _rule_fallback()

                return llm_result
            except (json.JSONDecodeError, ValueError) as e:
                logger = get_logger(__name__)
                logger.debug(f"LLM 返回 JSON 解析失败: {e}")
                # JSON 解析失败，回退到规则逻辑
                return _rule_fallback()
    except Exception as e:
        # LLM 调用失败，回退到规则逻辑
        logger = get_logger(__name__)
        logger.debug(f"LLM 调用失败: {e}")
        return _rule_fallback()

    # LLM 无有效 JSON 时兜底规则
    return _rule_fallback()


def _extract_explicit_paragraph_index(raw_text: str) -> int:
    paragraph_match = re.search(r"(?:在|给|将|把)?(?:第)?([一二三四五六七八九十\d]+)段", raw_text)
    if not paragraph_match:
        return -1
    para_str = paragraph_match.group(1)

    def _parse_zh_num(value: str) -> int:
        s = (value or "").strip()
        if not s:
            return 0
        if s.isdigit():
            return int(s)
        zh_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if s in zh_map:
            return zh_map[s]
        if s.startswith("十") and len(s) == 2 and s[1] in zh_map:
            return 10 + zh_map[s[1]]
        if len(s) == 2 and s[0] in zh_map and s[1] == "十":
            return zh_map[s[0]] * 10
        if len(s) == 3 and s[0] in zh_map and s[1] == "十" and s[2] in zh_map:
            return zh_map[s[0]] * 10 + zh_map[s[2]]
        return 0

    if para_str.isdigit():
        return int(para_str) - 1
    parsed = _parse_zh_num(para_str)
    return parsed - 1 if parsed > 0 else -1

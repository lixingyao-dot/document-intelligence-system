"""Markdown adapter for executing text-centric actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.llm.llm_service import get_llm_service
from utils.logger import get_logger

from .standard_style import get_standard_style_preset

logger = get_logger(__name__)


@dataclass
class ActionExecutionResult:
    action_type: str
    success: bool
    message: str
    details: Dict[str, Any]


class MdAdapter:
    """Adapter that applies action items to markdown files."""

    def __init__(self, file_path: str, llm_service=None):
        self.file_path = file_path
        self.content = Path(file_path).read_text(encoding="utf-8")
        self.execution_log: List[ActionExecutionResult] = []
        self._llm_service = llm_service
        self._document_understanding_cache: Optional[Dict[str, Any]] = None

    def apply_action(self, action: Dict[str, Any]) -> ActionExecutionResult:
        action_type = action.get("action_type", "")
        params = action.get("params", {}) or {}
        target = action.get("target", {}) or {}

        handler_map = {
            "bold_heading": self._apply_bold_heading,
            "unify_style": self._apply_unify_style,
            "reorder_paragraphs": self._apply_reorder_paragraphs,
            "replace_text": self._apply_replace_text,
            "extract_content": self._apply_extract_content,
            "clear_document_content": self._apply_clear_document_content,
            "remove_blank_lines": self._apply_remove_blank_lines,
        }

        handler = handler_map.get(action_type)
        if handler is None:
            result = ActionExecutionResult(action_type, False, f"MD 适配器暂不支持动作: {action_type}", {})
            self.execution_log.append(result)
            return result

        try:
            details = handler(target, params)
            result = ActionExecutionResult(action_type, True, "执行成功", details)
        except Exception as e:
            result = ActionExecutionResult(action_type, False, f"执行失败: {e}", {})

        self.execution_log.append(result)
        return result

    def save(self, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.content, encoding="utf-8")
        return str(path)

    # ── LLM 文档语义理解 ──────────────────────────────────────────

    @staticmethod
    def _safe_load_json(text: str) -> Optional[Dict[str, Any]]:
        """尝试从 LLM 响应中解析 JSON。"""
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
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    def _llm_chat(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """调用 LLM 获取结构化 JSON 结果，失败返回 None。"""
        llm = self._llm_service or get_llm_service()
        if not (llm and hasattr(llm, "is_available") and llm.is_available()):
            return None
        try:
            original_streaming = None
            can_toggle = hasattr(llm, "config") and hasattr(llm.config, "streaming")
            if can_toggle:
                original_streaming = llm.config.streaming
                llm.config.streaming = False
            try:
                raw = llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                )
            finally:
                if can_toggle:
                    llm.config.streaming = original_streaming
            return self._safe_load_json(raw)
        except Exception as exc:
            logger.warning("MdAdapter LLM 调用失败: %s", exc)
            return None

    def _get_document_understanding(self) -> Dict[str, Any]:
        """一次性 LLM 语义分析：识别标题、字段值、文档标题。结果缓存。"""
        if self._document_understanding_cache is not None:
            return self._document_understanding_cache

        lines = self.content.splitlines()
        non_empty = [(i, line.rstrip()) for i, line in enumerate(lines) if line.strip()]
        if not non_empty:
            self._document_understanding_cache = {}
            return self._document_understanding_cache

        items_text = "\n".join(f"{idx}: {text}" for idx, text in non_empty[:400])

        system_prompt = (
            "你是文档语义理解器。\n"
            "请基于以下 Markdown 文本内容，识别章节标题、关键字段值和文档总标题。\n"
            "标题可能是 # 语法标记的，也可能是没有标记但具有标题性质的短句。\n"
            "只输出 JSON，不要解释。"
        )
        user_prompt = (
            f"文本内容（行号:内容）:\n{items_text}\n\n"
            "输出格式:\n"
            '{"headings": [{"line": 行号, "title": "标题文本", "level": 级别}],'
            ' "field_values": {"字段名": "值"},'
            ' "document_title": {"title": "文档总标题", "line": 行号}}\n'
            "如果没有总标题，document_title 为 {\"title\": \"\", \"line\": -1}。\n"
            "headings 的 level 用数字表示：# = 1, ## = 2, 以此类推。无标记的标题性短句 level = 1。"
        )

        parsed = self._llm_chat(system_prompt, user_prompt)
        if not isinstance(parsed, dict):
            self._document_understanding_cache = {}
            return self._document_understanding_cache

        result: Dict[str, Any] = {}
        headings_raw = parsed.get("headings")
        if isinstance(headings_raw, list):
            result["headings"] = [
                h for h in headings_raw
                if isinstance(h, dict)
                and isinstance(h.get("line"), (int, float))
                and isinstance(h.get("title"), str) and h["title"].strip()
            ]
        else:
            result["headings"] = []

        fv = parsed.get("field_values")
        result["field_values"] = fv if isinstance(fv, dict) else {}

        dt = parsed.get("document_title")
        if isinstance(dt, dict) and isinstance(dt.get("title"), str) and dt["title"].strip():
            result["document_title"] = dt
        else:
            result["document_title"] = {"title": "", "line": -1}

        logger.info(
            "MdAdapter 文档理解: headings=%d, fields=%d",
            len(result["headings"]), len(result["field_values"]),
        )
        self._document_understanding_cache = result
        return self._document_understanding_cache

    def _apply_bold_heading(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        level = int(target.get("level", 1))
        heading_pattern = re.compile(rf"^(#{{{level}}})\s+(.*)$")
        updated = 0
        keep_trailing_newline = self.content.endswith("\n")
        lines = self.content.splitlines()
        new_lines: List[str] = []

        for line in lines:
            match = heading_pattern.match(line)
            if not match:
                new_lines.append(line)
                continue

            marker, title = match.group(1), match.group(2).strip()
            if not re.match(r"^\*\*.+\*\*$", title):
                title = f"**{title}**"
                updated += 1
            new_lines.append(f"{marker} {title}")

        # 若 markdown 语法未命中任何标题，尝试 LLM 语义识别
        if updated == 0:
            understanding = self._get_document_understanding()
            llm_headings = understanding.get("headings", [])
            if llm_headings:
                heading_lines = {
                    h["line"] for h in llm_headings
                    if isinstance(h.get("line"), int)
                    and int(h.get("level", 1)) == level
                }
                for i, line in enumerate(new_lines):
                    if i in heading_lines and line.strip() and not re.match(r"^\*\*.+\*\*$", line.strip()):
                        new_lines[i] = f"**{line.strip()}**"
                        updated += 1

        self.content = "\n".join(new_lines)
        if keep_trailing_newline:
            self.content += "\n"
        return {"level": level, "updated_headings": updated, "llm_heading_used": updated > 0 and heading_pattern.search("\n".join(lines)) is None}

    def _apply_unify_style(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        preset = get_standard_style_preset("md") if str(params.get("style_preset", "")).lower() == "standard" else {}
        lines = self.content.splitlines()
        normalized: List[str] = []

        for raw in lines:
            line = raw.rstrip()
            line = re.sub(r"^\s*[-*+]\s+", "- ", line)
            normalized.append(line)

        # 规范标题和列表前后空行
        with_spacing: List[str] = []
        for idx, line in enumerate(normalized):
            is_heading = bool(re.match(r"^#{1,6}\s+", line))
            is_list = bool(re.match(r"^-\s+", line))

            if (is_heading or is_list) and with_spacing and with_spacing[-1] != "":
                with_spacing.append("")

            with_spacing.append(line)

            next_line = normalized[idx + 1] if idx + 1 < len(normalized) else None
            if (is_heading or is_list) and next_line is not None and next_line.strip() and next_line != "":
                with_spacing.append("")

        text = "\n".join(with_spacing)
        text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
        self.content = text
        return {
            "strategy": params.get("strategy", preset.get("strategy", "standard")),
            "style_preset": params.get("style_preset", preset.get("style_preset", "standard")),
            "updated": True,
        }

    def _split_blocks(self) -> List[str]:
        parts = re.split(r"\n\s*\n", self.content.strip())
        return [p.strip("\n") for p in parts if p.strip()]

    @staticmethod
    def _is_heading_block(block: str) -> bool:
        for ln in block.splitlines():
            s = ln.strip()
            if not s:
                continue
            return bool(re.match(r"^#{1,6}\s+", s))
        return False

    def _locked_prefix_block_count(self, blocks: List[str]) -> int:
        """返回不可参与重排的前缀块数量（总标题/发布信息）。"""
        if not blocks:
            return 0

        def _first_line(block: str) -> str:
            for ln in block.splitlines():
                s = ln.strip()
                if s:
                    return s
            return ""

        locked = 0
        first = _first_line(blocks[0])
        if re.match(r"^#{1,2}\s+", first):
            locked = 1

        meta_keywords = ("发布时间", "发布", "统计局", "调查队", "日期")
        while locked < len(blocks):
            block = blocks[locked]
            block_text = block.strip()
            if not block_text:
                locked += 1
                continue
            if len(block_text) <= 120 and any(k in block_text for k in meta_keywords):
                locked += 1
                continue
            break

        return locked

    def _apply_reorder_paragraphs(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        blocks = self._split_blocks()
        locked_prefix = self._locked_prefix_block_count(blocks)
        index_basis = str(params.get("index_basis", "body_paragraph") or "body_paragraph").lower()
        movable_positions = [
            i for i in range(locked_prefix, len(blocks))
            if not self._is_heading_block(blocks[i])
        ]
        movable_blocks = [blocks[i] for i in movable_positions]
        from_idx = int(params.get("from", 0))
        to_idx = int(params.get("to", 0))

        if from_idx <= 0 or to_idx <= 0 or from_idx > len(movable_blocks) or to_idx > len(movable_blocks):
            return {
                "moved": False,
                "reason": "索引越界",
                "from": from_idx,
                "to": to_idx,
                "locked_prefix_blocks": locked_prefix,
                "index_basis": index_basis,
                "movable_blocks": len(movable_blocks),
            }

        block = movable_blocks.pop(from_idx - 1)
        movable_blocks.insert(to_idx - 1, block)

        for idx, pos in enumerate(movable_positions):
            blocks[pos] = movable_blocks[idx]

        self.content = "\n\n".join(blocks) + "\n"
        return {
            "moved": True,
            "from": from_idx,
            "to": to_idx,
            "locked_prefix_blocks": locked_prefix,
            "index_basis": index_basis,
            "movable_blocks": len(movable_positions),
        }

    def _apply_replace_text(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        find_text = str(params.get("find", ""))
        replace_text = str(params.get("replace", ""))
        if not find_text:
            return {"find": find_text, "replace": replace_text, "replaced": 0}

        count = self.content.count(find_text)
        self.content = self.content.replace(find_text, replace_text)
        return {"find": find_text, "replace": replace_text, "replaced": count}

    def _apply_extract_content(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        headings = [line.strip() for line in self.content.splitlines() if re.match(r"^#{1,6}\s+", line.strip())]
        blocks = self._split_blocks()
        fields = params.get("fields", []) if isinstance(params.get("fields"), list) else []
        extracted: Dict[str, str] = {}

        for field in fields:
            key = str(field).strip()
            if not key:
                continue
            pattern = rf"{re.escape(key)}\s*[:：]\s*([^\n]+)"
            m = re.search(pattern, self.content)
            if m:
                extracted[key] = m.group(1).strip()

        # LLM 语义补充：标题、字段值、文档标题
        llm_understanding_used = False
        understanding = self._get_document_understanding()
        if understanding:
            llm_headings = understanding.get("headings", [])
            if llm_headings:
                semantic_titles = [h["title"] for h in llm_headings if h.get("title")]
                # 合并去重
                seen = set(headings)
                for t in semantic_titles:
                    if t not in seen:
                        headings.append(t)
                        seen.add(t)
                llm_understanding_used = True

            llm_fields = understanding.get("field_values", {})
            if isinstance(llm_fields, dict):
                for k, v in llm_fields.items():
                    if k not in extracted and v:
                        extracted[k] = str(v)
                        llm_understanding_used = True

        result = {
            "headings": headings,
            "blocks": blocks,
            "fields": extracted,
            "summary": "\n".join(blocks[:3]),
            "llm_understanding_used": llm_understanding_used,
        }

        doc_title = understanding.get("document_title") if understanding else None
        if isinstance(doc_title, dict) and doc_title.get("title"):
            result["document_title"] = doc_title["title"]

        return result

    def _apply_clear_document_content(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        previous_chars = len(self.content or "")
        self.content = ""
        return {"scope": str(target.get("scope", "document")), "cleared_characters": previous_chars}

    def _apply_remove_blank_lines(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        before = len(re.findall(r"\n\s*\n", self.content))
        self.content = re.sub(r"\n{3,}", "\n\n", self.content)
        after = len(re.findall(r"\n\s*\n", self.content))
        return {"removed": max(0, before - after)}

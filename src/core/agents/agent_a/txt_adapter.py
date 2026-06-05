"""TXT adapter for executing plain-text actions."""

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


class TxtAdapter:
    """Adapter that applies action items to txt files."""

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
            "reorder_paragraphs": self._apply_reorder_paragraphs,
            "replace_text": self._apply_replace_text,
            "extract_content": self._apply_extract_content,
            "clear_document_content": self._apply_clear_document_content,
            "remove_blank_lines": self._apply_remove_blank_lines,
            "unify_style": self._apply_unify_style,
            "split_paragraphs": self._apply_split_paragraphs,
        }

        handler = handler_map.get(action_type)
        if handler is None:
            result = ActionExecutionResult(action_type, False, f"TXT 适配器暂不支持动作: {action_type}", {})
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
            logger.warning("TxtAdapter LLM 调用失败: %s", exc)
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
            "请基于以下纯文本内容，识别章节标题、关键字段值和文档总标题。\n"
            "标题可能是中文编号格式（一、二、（一）、1. 等）或没有标记但具有标题性质的短句。\n"
            "只输出 JSON，不要解释。"
        )
        user_prompt = (
            f"文本内容（行号:内容）:\n{items_text}\n\n"
            "输出格式:\n"
            '{"headings": [{"line": 行号, "title": "标题文本", "level": 级别}],'
            ' "field_values": {"字段名": "值"},'
            ' "document_title": {"title": "文档总标题", "line": 行号}}\n'
            "如果没有总标题，document_title 为 {\"title\": \"\", \"line\": -1}。\n"
            "level 参考：一级标题 1，二级标题 2，以此类推。"
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
            "TxtAdapter 文档理解: headings=%d, fields=%d",
            len(result["headings"]), len(result["field_values"]),
        )
        self._document_understanding_cache = result
        return self._document_understanding_cache

    def _split_blocks(self) -> List[str]:
        raw = self.content.strip()
        if not raw:
            return []

        parts = [p.strip("\n") for p in re.split(r"\n\s*\n", raw) if p.strip()]
        # 真实 txt 往往没有空行，回退到按非空行分段，避免重排索引越界。
        if len(parts) <= 1:
            parts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        return parts

    @staticmethod
    def _is_heading_unit(unit: str) -> bool:
        s = (unit or "").strip()
        if not s:
            return False
        patterns = [
            r"^第?[一二三四五六七八九十]+、",          # 一、 二、
            r"^[（(][一二三四五六七八九十]+[）)]",      # （一） (一)
            r"^#{1,6}\s+",                          # markdown 风格标题
        ]
        return any(re.match(p, s) for p in patterns)

    def _locked_prefix_unit_count(self, units: List[str]) -> int:
        """识别并锁定前缀（主标题/元信息），避免被正文重排移动。"""
        if not units:
            return 0

        locked = 0
        first = (units[0] or "").strip()
        second = (units[1] or "").strip() if len(units) > 1 else ""

        # 若第二行是结构化标题（如“一、”/“（一）”），第一行大概率是总标题，锁定。
        if second and self._is_heading_unit(second):
            locked = 1
        # 显式报告类标题也锁定。
        elif len(first) <= 80 and re.search(r"报告|公报|分析|白皮书|年报", first):
            locked = 1

        meta_keywords = ("发布时间", "发布", "来源", "统计局", "调查队", "日期")
        while locked < len(units):
            text = (units[locked] or "").strip()
            if not text:
                locked += 1
                continue
            if len(text) <= 120 and any(k in text for k in meta_keywords):
                locked += 1
                continue
            break

        return locked

    def _apply_split_paragraphs(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        blocks = self._split_blocks()
        return {"blocks": blocks, "count": len(blocks)}

    def _apply_reorder_paragraphs(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        blocks = self._split_blocks()
        index_basis = str(params.get("index_basis", "body_paragraph") or "body_paragraph").lower()
        locked_prefix = self._locked_prefix_unit_count(blocks)

        movable_positions = [
            i for i, block in enumerate(blocks)
            if i >= locked_prefix
            if not self._is_heading_unit(block)
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
                "index_basis": index_basis,
                "movable_blocks": len(movable_blocks),
                "locked_prefix_units": locked_prefix,
            }

        block = movable_blocks.pop(from_idx - 1)
        # 自然语言“移动到第N段之后”采用 after 语义。
        insert_idx = to_idx
        if from_idx < to_idx:
            # 先 pop 会导致目标索引左移一位。
            insert_idx -= 1
        insert_idx = max(0, min(insert_idx, len(movable_blocks)))
        movable_blocks.insert(insert_idx, block)

        for idx, pos in enumerate(movable_positions):
            blocks[pos] = movable_blocks[idx]

        self.content = "\n\n".join(blocks) + "\n"
        return {
            "moved": True,
            "from": from_idx,
            "to": to_idx,
            "index_basis": index_basis,
            "movable_blocks": len(movable_blocks),
            "locked_prefix_units": locked_prefix,
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
        headings: List[str] = []
        llm_understanding_used = False
        understanding = self._get_document_understanding()
        if understanding:
            llm_headings = understanding.get("headings", [])
            if llm_headings:
                headings = [h["title"] for h in llm_headings if h.get("title")]
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

    def _apply_unify_style(self, target: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        preset = get_standard_style_preset("txt") if str(params.get("style_preset", "")).lower() == "standard" else {}
        lines = [ln.rstrip() for ln in self.content.splitlines()]
        text = "\n".join(lines)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
        self.content = text
        return {
            "updated": True,
            "strategy": params.get("strategy", preset.get("strategy", "standard")),
            "style_preset": params.get("style_preset", preset.get("style_preset", "standard")),
        }

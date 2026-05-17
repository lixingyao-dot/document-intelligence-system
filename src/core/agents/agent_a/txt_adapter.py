"""TXT adapter for executing plain-text actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .standard_style import get_standard_style_preset


@dataclass
class ActionExecutionResult:
    action_type: str
    success: bool
    message: str
    details: Dict[str, Any]


class TxtAdapter:
    """Adapter that applies action items to txt files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = Path(file_path).read_text(encoding="utf-8")
        self.execution_log: List[ActionExecutionResult] = []

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

        return {
            "blocks": blocks,
            "fields": extracted,
            "summary": "\n".join(blocks[:3]),
        }

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

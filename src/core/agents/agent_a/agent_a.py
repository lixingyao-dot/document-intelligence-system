"""Agent_A: 文档编辑 Agent 最小可运行骨架。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import SystemConfig
from core.orchestrator.task_spec import TaskSpec
from core.agents.base_agent import BaseAgent, AgentResponse
from core.llm.llm_service import get_llm_service
from .action_plan import build_action_plan_from_instruction
from .edit_message import summarize_edit_execution
from .capability_matrix import validate_action_plan_against_files
from .docx_adapter import DocxAdapter
from .md_adapter import MdAdapter
from .txt_adapter import TxtAdapter
from .xlsx_adapter import XlsxAdapter


def _has_mutating_edit(execution_report: list) -> bool:
	return any(
		item.get("success") and item.get("action_type") not in ("extract_content",)
		for item in (execution_report or [])
	)


def _is_output_rename_instruction(text: str) -> bool:
	return bool(
		re.search(r"(?:输出)?(?:文件)?名(?:字)?改为\s*[^\s，。,；;]+", text or "", flags=re.IGNORECASE)
	) and not re.search(r"(?:将|把)\s*\S+\s*改为", text or "")


class AgentA(BaseAgent):
	"""
	Agent_A 最小骨架。

	当前阶段只返回固定结构化结果，不执行真实文档编辑。
	"""

	def __init__(self, config: Optional[SystemConfig] = None):
		super().__init__(config)
		self.name = "Agent_A"
		self.agent_type = "document_editing"

	def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
		"""执行文档编辑任务（最小骨架实现）。"""
		is_valid, error_msg = self.validate_input(task_spec)
		if not is_valid:
			return AgentResponse(success=False, message=error_msg)

		instruction = task_spec.instruction or ""
		source_paths = [f.path for f in task_spec.source_files]
		action_plan = build_action_plan_from_instruction(instruction)
		precheck = validate_action_plan_against_files(action_plan, task_spec.source_files)

		if not precheck.is_valid:
			first_error = precheck.errors[0] if precheck.errors else {}
			return AgentResponse(
				success=False,
				message=(
					"执行前校验失败: "
					f"动作 {first_error.get('action_type', 'unknown')} 与文件类型 "
					f"{first_error.get('file_type', 'unknown')} 不兼容。"
				),
				data={
					"status": "precheck_failed",
					"action_plan": action_plan.model_dump(),
					"validation_errors": precheck.errors,
					"suggestions": [e.get("suggestion") for e in precheck.errors if e.get("suggestion")],
				},
				metadata={
					"agent": self.name,
					"stage": "precheck_failed",
				},
			)

		docx_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "docx"), None)
		md_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "md"), None)
		txt_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "txt"), None)
		xlsx_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "xlsx"), None)
		real_edit_executed = False
		execution_report = []
		extraction_outputs = []
		output_file = task_spec.output_file

		def _default_output_path(source_path: Path) -> str:
			return str(source_path.with_name(f"{source_path.stem}_edited{source_path.suffix}"))

		def _desired_output_from_instruction(text: str, source_path: Path) -> Optional[str]:
			"""解析「文件名/名字改为 XXX」为输出文件名。"""
			m = re.search(
				r"(?:输出)?(?:文件)?名(?:字)?改为\s*([^\s，。,；;]+)",
				text or "",
				flags=re.IGNORECASE,
			)
			if not m:
				return None
			raw = m.group(1).strip().strip("\"'“”")
			if not raw:
				return None
			name = raw if raw.lower().endswith(source_path.suffix.lower()) else f"{raw}{source_path.suffix}"
			return str(source_path.parent / Path(name).name)

		if docx_file and Path(docx_file.path).exists():
			source_path = Path(docx_file.path).resolve()
			adapter = DocxAdapter(docx_file.path, llm_service=get_llm_service())
			for action in action_plan.model_dump().get("actions", []):
				result = adapter.apply_action(action)
				execution_report.append(
					{
						"action_type": result.action_type,
						"success": result.success,
						"message": result.message,
						"details": result.details,
					}
				)
				if result.action_type == "extract_content" and result.success:
					extraction_outputs.append(result.details)

			if not output_file:
				output_file = _desired_output_from_instruction(instruction, source_path) or _default_output_path(source_path)
			output_file = adapter.save(output_file)
			real_edit_executed = _has_mutating_edit(execution_report) or (
				_is_output_rename_instruction(instruction)
				and Path(output_file).name != source_path.name
			)

		elif md_file and Path(md_file.path).exists():
			source_path = Path(md_file.path).resolve()
			adapter = MdAdapter(md_file.path)
			for action in action_plan.model_dump().get("actions", []):
				result = adapter.apply_action(action)
				execution_report.append(
					{
						"action_type": result.action_type,
						"success": result.success,
						"message": result.message,
						"details": result.details,
					}
				)
				if result.action_type == "extract_content" and result.success:
					extraction_outputs.append(result.details)

			if not output_file:
				output_file = _desired_output_from_instruction(instruction, source_path) or _default_output_path(source_path)
			output_file = adapter.save(output_file)
			real_edit_executed = _has_mutating_edit(execution_report) or (
				_is_output_rename_instruction(instruction)
				and Path(output_file).name != source_path.name
			)

		elif txt_file and Path(txt_file.path).exists():
			source_path = Path(txt_file.path).resolve()
			adapter = TxtAdapter(txt_file.path)
			for action in action_plan.model_dump().get("actions", []):
				result = adapter.apply_action(action)
				execution_report.append(
					{
						"action_type": result.action_type,
						"success": result.success,
						"message": result.message,
						"details": result.details,
					}
				)
				if result.action_type == "extract_content" and result.success:
					extraction_outputs.append(result.details)

			if not output_file:
				output_file = _desired_output_from_instruction(instruction, source_path) or _default_output_path(source_path)
			output_file = adapter.save(output_file)
			real_edit_executed = _has_mutating_edit(execution_report) or (
				_is_output_rename_instruction(instruction)
				and Path(output_file).name != source_path.name
			)

		elif xlsx_file and Path(xlsx_file.path).exists():
			source_path = Path(xlsx_file.path).resolve()
			adapter = XlsxAdapter(xlsx_file.path)
			for action in action_plan.model_dump().get("actions", []):
				result = adapter.apply_action(action)
				execution_report.append(
					{
						"action_type": result.action_type,
						"success": result.success,
						"message": result.message,
						"details": result.details,
					}
				)
				if result.action_type == "extract_content" and result.success:
					extraction_outputs.append(result.details)

			if not output_file:
				output_file = _desired_output_from_instruction(instruction, source_path) or _default_output_path(source_path)
			output_file = adapter.save(output_file)
			real_edit_executed = _has_mutating_edit(execution_report) or (
				_is_output_rename_instruction(instruction)
				and Path(output_file).name != source_path.name
			)

		if real_edit_executed:
			message = summarize_edit_execution(instruction, execution_report)
		else:
			message = "未能执行文档编辑：未识别到可执行操作或文件不可用。"
		return AgentResponse(
			success=real_edit_executed,
			message=message,
			data={
				"status": "completed" if real_edit_executed else "ready",
				"mode": "document_editing",
				"instruction": instruction,
				"source_files": source_paths,
				"intent": action_plan.intent,
				"action_plan": action_plan.model_dump(),
				"actions": [a["action_type"] for a in action_plan.model_dump()["actions"]],
				"precheck": {
					"passed": True,
					"hints": precheck.hints,
				},
				"edited": real_edit_executed,
				"output_file": output_file,
				"execution_report": execution_report,
				"extraction": extraction_outputs,
			},
			metadata={
				"agent": self.name,
				"stage": "docx_executed" if real_edit_executed else "action_plan_defined",
			},
		)

	def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
		"""最小输入校验。"""
		if not task_spec.source_files:
			return False, "缺少源文件"
		return True, ""

	def get_capabilities(self) -> Dict[str, Any]:
		"""返回 Agent 能力说明。"""
		return {
			"name": self.name,
			"type": self.agent_type,
			"description": "文档编辑 Agent 最小骨架（第一步）",
			"supported_formats": ["docx", "md", "xlsx", "txt"],
			"features": [
				"接收文档编辑任务",
				"返回固定结构化结果",
				"为后续动作规划与执行预留接口",
			],
		}


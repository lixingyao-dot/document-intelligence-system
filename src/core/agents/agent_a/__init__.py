"""Agent A package exports."""

from .agent_a import AgentA
from .action_plan import ActionPlan, ActionItem, ActionType, build_action_plan_from_instruction, validate_action_plan_schema
from .instruction_parser import parse_instruction_rule_first, parse_instruction_with_llm_fallback
from .capability_matrix import ACTION_FILE_COMPATIBILITY, PrecheckResult, validate_action_plan_against_files
from .docx_adapter import DocxAdapter
from .editor_api import edit_document_with_agent_a
from .md_adapter import MdAdapter
from .txt_adapter import TxtAdapter
from .xlsx_adapter import XlsxAdapter

__all__ = [
	"AgentA",
	"ActionPlan",
	"ActionItem",
	"ActionType",
	"ACTION_FILE_COMPATIBILITY",
	"PrecheckResult",
	"DocxAdapter",
	"MdAdapter",
	"TxtAdapter",
	"XlsxAdapter",
	"parse_instruction_rule_first",
	"parse_instruction_with_llm_fallback",
	"build_action_plan_from_instruction",
	"validate_action_plan_against_files",
	"validate_action_plan_schema",
	"edit_document_with_agent_a",
]

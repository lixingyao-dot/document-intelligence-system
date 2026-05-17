"""
任务与抽取结果持久化（对齐 sql/schema_v1.sql）。

子模块：types / queries / audit / mutations / extraction / artifacts / timeline / review
"""
from __future__ import annotations

from .artifacts import insert_agent_log, insert_document_asset, insert_fill_report
from .audit import insert_audit_log, insert_audit_log_conn, insert_task_step
from .extraction import (
    resolve_task_id,
    save_extraction_from_agent_payload,
    save_extraction_from_agent_payload_safe,
)
from .mutations import (
    ensure_task,
    mark_task_failed,
    mark_task_succeeded,
    next_extraction_version,
    save_extraction_result,
)
from .queries import (
    get_latest_extraction_by_task_id,
    get_latest_extraction_by_task_uuid,
    get_task_by_task_id,
    get_task_by_task_id_in_conn,
    get_task_by_uuid,
    list_tasks,
)
from .review import set_task_review
from .timeline import get_task_timeline
from .types import (
    ExtractionResultRow,
    SaveExtractionOutcome,
    TaskListPage,
    TaskRow,
)

__all__ = [
    "ExtractionResultRow",
    "SaveExtractionOutcome",
    "TaskListPage",
    "TaskRow",
    "ensure_task",
    "get_latest_extraction_by_task_id",
    "get_latest_extraction_by_task_uuid",
    "get_task_by_task_id",
    "get_task_by_task_id_in_conn",
    "get_task_by_uuid",
    "get_task_timeline",
    "insert_agent_log",
    "insert_audit_log",
    "insert_audit_log_conn",
    "insert_document_asset",
    "insert_fill_report",
    "insert_task_step",
    "list_tasks",
    "mark_task_failed",
    "mark_task_succeeded",
    "next_extraction_version",
    "resolve_task_id",
    "save_extraction_from_agent_payload",
    "save_extraction_from_agent_payload_safe",
    "save_extraction_result",
    "set_task_review",
]

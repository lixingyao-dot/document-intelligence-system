"""Repository 数据类与行映射。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SaveExtractionOutcome:
    task_id: str
    task_uuid: str
    extraction_id: str
    result_version: int


@dataclass
class TaskRow:
    """tasks 表一行（供 API / CLI 展示）"""

    id: str
    task_id: str
    task_type: str
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    parent_task_id: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass
class ExtractionResultRow:
    """extraction_results 表一行"""

    id: str
    task_uuid: str
    schema_version: str
    payload: Dict[str, Any]
    result_version: int
    created_at: datetime


@dataclass
class TaskListPage:
    """任务列表分页结果"""

    items: List[TaskRow]
    total: int
    limit: int
    offset: int


def row_to_task(row: Dict[str, Any]) -> TaskRow:
    return TaskRow(
        id=row["id"],
        task_id=row["task_id"],
        task_type=row["task_type"],
        status=row["status"],
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        parent_task_id=row.get("parent_task_id"),
        metadata=row["metadata"] if isinstance(row["metadata"], dict) else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )


def row_to_extraction(row: Dict[str, Any]) -> ExtractionResultRow:
    pl = row["payload"]
    if not isinstance(pl, dict):
        pl = {}
    return ExtractionResultRow(
        id=row["id"],
        task_uuid=row["task_uuid"],
        schema_version=row["schema_version"],
        payload=pl,
        result_version=int(row["result_version"]),
        created_at=row["created_at"],
    )

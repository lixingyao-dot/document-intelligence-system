"""任务链路聚合。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from config import SystemConfig, get_config
from db.connection import db_connection

from .queries import get_task_by_task_id


def get_task_timeline(
    task_id: str,
    config: Optional[SystemConfig] = None,
) -> Optional[Dict[str, Any]]:
    """聚合任务、task_steps、audit_logs（subject 为业务 task_id）。"""
    cfg = config or get_config()
    task = get_task_by_task_id(task_id, cfg)
    if not task:
        return None
    tu = task.id
    steps_out: List[Dict[str, Any]] = []
    audits_out: List[Dict[str, Any]] = []
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, step_name, step_order, status, detail,
                       error_code, error_message, started_at, completed_at, created_at
                FROM task_steps
                WHERE task_uuid = %s::uuid
                ORDER BY step_order ASC, created_at ASC
                """,
                (tu,),
            )
            for r in cur.fetchall():
                d = dict(r)
                for k in ("started_at", "completed_at", "created_at"):
                    if d.get(k) is not None:
                        d[k] = d[k].isoformat() if hasattr(d[k], "isoformat") else d[k]
                steps_out.append(d)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, occurred_at, actor, subject_type, subject_id, event, payload
                FROM audit_logs
                WHERE subject_type = 'task' AND subject_id = %s
                ORDER BY occurred_at ASC
                """,
                (task_id,),
            )
            for r in cur.fetchall():
                d = dict(r)
                if d.get("occurred_at"):
                    d["occurred_at"] = d["occurred_at"].isoformat()
                audits_out.append(d)
    return {
        "task": {
            "id": task.id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "metadata": task.metadata,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        },
        "steps": steps_out,
        "audit_logs": audits_out,
    }

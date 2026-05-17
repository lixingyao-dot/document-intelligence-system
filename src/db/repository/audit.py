"""审计与 task_steps。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from psycopg.types.json import Json

from config import SystemConfig, get_config
from db.connection import db_connection

from .types import utc_now


def insert_audit_log_conn(
    conn,
    subject_type: str,
    subject_id: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    actor: str = "system",
) -> str:
    """在同一连接/事务内写入 audit_logs。"""
    pl = payload or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (actor, subject_type, subject_id, event, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (actor, subject_type, subject_id, event, Json(pl)),
        )
        return str(cur.fetchone()[0])


def insert_task_step(
    conn,
    task_uuid: str,
    step_name: str,
    *,
    step_order: int = 0,
    status: str = "succeeded",
    detail: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    """写入 task_steps。status: queued|running|succeeded|failed|skipped"""
    now = utc_now()
    if status == "running":
        started_at, completed_at = now, None
    else:
        started_at, completed_at = now, now
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO task_steps (
                task_uuid, step_name, step_order, status, detail,
                error_code, error_message, started_at, completed_at
            )
            VALUES (
                %s::uuid, %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s
            )
            RETURNING id::text
            """,
            (
                task_uuid,
                step_name,
                step_order,
                status,
                Json(detail or {}),
                error_code,
                error_message,
                started_at,
                completed_at,
            ),
        )
        return str(cur.fetchone()[0])


def insert_audit_log(
    subject_type: str,
    subject_id: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    actor: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> str:
    """独立事务写入 audit_logs。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.transaction():
            return insert_audit_log_conn(
                conn,
                subject_type,
                subject_id,
                event,
                payload,
                actor or "system",
            )

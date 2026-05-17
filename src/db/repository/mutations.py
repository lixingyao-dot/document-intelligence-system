"""任务行与抽取结果行级变更（事务内）。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from psycopg.types.json import Json

from .audit import insert_audit_log_conn
from .types import utc_now


def ensure_task(
    conn,
    task_id: str,
    task_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """确保 tasks 中存在 task_id 对应行，返回内部 UUID（字符串形式）。"""
    meta = metadata or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (task_id, task_type, status, metadata, started_at)
            VALUES (%s, %s, 'running', %s::jsonb, %s)
            ON CONFLICT (task_id) DO UPDATE SET
                updated_at = now(),
                task_type = EXCLUDED.task_type
            RETURNING id::text
            """,
            (task_id, task_type, Json(meta), utc_now()),
        )
        row = cur.fetchone()
        task_uuid = row[0]
        insert_audit_log_conn(
            conn,
            "task",
            task_id,
            "task_upserted",
            {"task_uuid": task_uuid, "task_type": task_type},
        )
        return task_uuid


def next_extraction_version(conn, task_uuid: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(MAX(result_version), 0) + 1
            FROM extraction_results
            WHERE task_uuid = %s::uuid
            """,
            (task_uuid,),
        )
        return int(cur.fetchone()[0])


def save_extraction_result(
    conn,
    task_uuid: str,
    schema_version: str,
    payload: Dict[str, Any],
) -> Tuple[str, int]:
    """写入 extraction_results，返回 (新行 id, result_version)。"""
    ver = next_extraction_version(conn, task_uuid)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO extraction_results (task_uuid, schema_version, payload, result_version)
            VALUES (%s::uuid, %s, %s::jsonb, %s)
            RETURNING id::text, result_version
            """,
            (task_uuid, schema_version, Json(payload), ver),
        )
        rid, rv = cur.fetchone()
        return str(rid), int(rv)


def mark_task_succeeded(
    conn,
    task_uuid: str,
    task_business_id: str,
) -> None:
    now = utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'succeeded',
                error_code = NULL,
                error_message = NULL,
                updated_at = %s,
                completed_at = %s
            WHERE id = %s::uuid
            """,
            (now, now, task_uuid),
        )
    insert_audit_log_conn(
        conn,
        "task",
        task_business_id,
        "task_status_succeeded",
        {"task_uuid": task_uuid},
    )


def mark_task_failed(
    conn,
    task_uuid: str,
    error_code: str,
    error_message: str,
    task_business_id: str,
) -> None:
    now = utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'failed',
                error_code = %s,
                error_message = %s,
                updated_at = %s,
                completed_at = %s
            WHERE id = %s::uuid
            """,
            (error_code, error_message[:2000], now, now, task_uuid),
        )
    insert_audit_log_conn(
        conn,
        "task",
        task_business_id,
        "task_status_failed",
        {
            "task_uuid": task_uuid,
            "error_code": error_code,
            "message": error_message[:500],
        },
    )

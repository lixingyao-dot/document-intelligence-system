"""任务与抽取结果查询。"""
from __future__ import annotations

from typing import Optional

from psycopg.rows import dict_row

from config import SystemConfig, get_config
from db.connection import db_connection

from .types import (
    ExtractionResultRow,
    TaskListPage,
    TaskRow,
    row_to_extraction,
    row_to_task,
)


def get_task_by_task_id(
    task_id: str,
    config: Optional[SystemConfig] = None,
) -> Optional[TaskRow]:
    """按业务 task_id 查询任务。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, task_id, task_type, status, error_code, error_message,
                       parent_task_id::text AS parent_task_id, metadata,
                       created_at, updated_at, started_at, completed_at
                FROM tasks
                WHERE task_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()
            return row_to_task(row) if row else None


def get_task_by_task_id_in_conn(conn, task_id: str) -> Optional[TaskRow]:
    """在同一连接内查询任务（供事务内使用）。"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id::text AS id, task_id, task_type, status, error_code, error_message,
                   parent_task_id::text AS parent_task_id, metadata,
                   created_at, updated_at, started_at, completed_at
            FROM tasks
            WHERE task_id = %s
            """,
            (task_id,),
        )
        row = cur.fetchone()
        return row_to_task(row) if row else None


def get_task_by_uuid(
    task_uuid: str,
    config: Optional[SystemConfig] = None,
) -> Optional[TaskRow]:
    """按内部 UUID（tasks.id）查询任务。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, task_id, task_type, status, error_code, error_message,
                       parent_task_id::text AS parent_task_id, metadata,
                       created_at, updated_at, started_at, completed_at
                FROM tasks
                WHERE id = %s::uuid
                """,
                (task_uuid,),
            )
            row = cur.fetchone()
            return row_to_task(row) if row else None


def get_latest_extraction_by_task_id(
    task_id: str,
    config: Optional[SystemConfig] = None,
) -> Optional[ExtractionResultRow]:
    """按业务 task_id 取最新一条抽取结果。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT er.id::text AS id, er.task_uuid::text AS task_uuid, er.schema_version,
                       er.payload, er.result_version, er.created_at
                FROM extraction_results er
                INNER JOIN tasks t ON t.id = er.task_uuid
                WHERE t.task_id = %s
                ORDER BY er.result_version DESC, er.created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cur.fetchone()
            return row_to_extraction(row) if row else None


def get_latest_extraction_by_task_uuid(
    task_uuid: str,
    config: Optional[SystemConfig] = None,
) -> Optional[ExtractionResultRow]:
    """按 tasks.id 取最新一条抽取结果。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, task_uuid::text AS task_uuid, schema_version,
                       payload, result_version, created_at
                FROM extraction_results
                WHERE task_uuid = %s::uuid
                ORDER BY result_version DESC, created_at DESC
                LIMIT 1
                """,
                (task_uuid,),
            )
            row = cur.fetchone()
            return row_to_extraction(row) if row else None


def list_tasks(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> TaskListPage:
    """任务列表分页，按 created_at 降序。"""
    cfg = config or get_config()
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COUNT(*)::bigint AS c FROM tasks
                WHERE (%s::text IS NULL OR status = %s::text)
                """,
                (status, status),
            )
            total = int(cur.fetchone()["c"])
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, task_id, task_type, status, error_code, error_message,
                       parent_task_id::text AS parent_task_id, metadata,
                       created_at, updated_at, started_at, completed_at
                FROM tasks
                WHERE (%s::text IS NULL OR status = %s::text)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (status, status, lim, off),
            )
            rows = cur.fetchall()
    items = [row_to_task(dict(r)) for r in rows]
    return TaskListPage(items=items, total=total, limit=lim, offset=off)

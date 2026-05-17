"""人工复核状态迁移。"""
from __future__ import annotations

from typing import Optional

from config import SystemConfig, get_config
from db.connection import db_connection

from .audit import insert_audit_log_conn
from .queries import get_task_by_task_id_in_conn
from .types import utc_now


def set_task_review(
    task_id: str,
    action: str,
    *,
    comment: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> None:
    """
    人工复核状态迁移。action:
    - mark_review: running/succeeded -> review
    - approve: review -> succeeded
    - reject: review -> failed
    """
    if action not in ("mark_review", "approve", "reject"):
        raise ValueError("action 须为 mark_review | approve | reject")
    cfg = config or get_config()
    now = utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            row = get_task_by_task_id_in_conn(conn, task_id)
            if not row:
                raise ValueError(f"任务不存在: {task_id}")
            tu = row.id
            st = row.status
            if action == "mark_review":
                if st not in ("running", "succeeded"):
                    raise ValueError(f"当前状态不可标为 review: {st}")
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE tasks SET status = 'review', updated_at = %s
                        WHERE id = %s::uuid
                        """,
                        (now, tu),
                    )
                insert_audit_log_conn(
                    conn,
                    "task",
                    task_id,
                    "task_marked_review",
                    {"comment": comment or "", "task_uuid": tu},
                )
            elif action == "approve":
                if st != "review":
                    raise ValueError(f"仅 review 状态可 approve，当前: {st}")
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE tasks SET status = 'succeeded', error_code = NULL, error_message = NULL,
                            updated_at = %s, completed_at = %s
                        WHERE id = %s::uuid
                        """,
                        (now, now, tu),
                    )
                insert_audit_log_conn(
                    conn,
                    "task",
                    task_id,
                    "review_approved",
                    {"comment": comment or "", "task_uuid": tu},
                )
            else:
                if st != "review":
                    raise ValueError(f"仅 review 状态可 reject，当前: {st}")
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE tasks SET status = 'failed', error_code = %s, error_message = %s,
                            updated_at = %s, completed_at = %s
                        WHERE id = %s::uuid
                        """,
                        (
                            "REVIEW_REJECTED",
                            (comment or "复核驳回")[:2000],
                            now,
                            now,
                            tu,
                        ),
                    )
                insert_audit_log_conn(
                    conn,
                    "task",
                    task_id,
                    "review_rejected",
                    {"comment": comment or "", "task_uuid": tu},
                )

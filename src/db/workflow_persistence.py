"""
工作流编排与数据库对齐：在 WorkflowCoordinator 入口写 tasks / task_steps / audit。

DB 未启用或仅内存演示时自动跳过。

注意：不 import core.orchestrator，避免与 coordinator 循环依赖；对 TaskSpec 采用 duck typing。
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured
from db.repository import (
    ensure_task,
    get_task_by_task_id_in_conn,
    insert_audit_log_conn,
    insert_task_step,
    mark_task_failed,
    mark_task_succeeded,
)


def _task_business_id(spec: Any) -> str:
    tid = spec.parameters.get("task_id")
    if tid:
        return str(tid)
    if spec.session_id:
        return str(spec.session_id)
    return uuid.uuid4().hex[:12]


def persist_workflow_execute_begin(
    spec: Any,
    config: Optional[SystemConfig] = None,
) -> Optional[str]:
    """
    在任务校验通过后、执行 handler 前调用。
    写入/更新 tasks（running）、task_steps orchestrator_start、审计 workflow_started。
    将业务 task_id 写入 spec.parameters['task_id'] 供后续 Agent/入库对齐。
    返回 task_id；未写库时仍返回 task_id 字符串供逻辑使用。
    """
    cfg = config or get_config()
    task_id = _task_business_id(spec)
    spec.parameters["task_id"] = task_id
    spec.parameters["task_uuid"] = None

    if not cfg.database.enabled or not is_database_configured(cfg):
        return task_id

    tt = getattr(spec.task_type, "value", str(spec.task_type))
    with db_connection(cfg) as conn:
        with conn.transaction():
            tu = ensure_task(
                conn,
                task_id,
                tt,
                metadata={
                    "session_id": spec.session_id,
                    "source": "workflow_coordinator",
                },
            )
            spec.parameters["task_uuid"] = str(tu)
            insert_task_step(
                conn,
                tu,
                "orchestrator_start",
                step_order=0,
                status="succeeded",
                detail={"task_type": tt},
            )
            insert_audit_log_conn(
                conn,
                "task",
                task_id,
                "workflow_started",
                {"task_uuid": tu, "task_type": tt},
            )
    return task_id


def persist_workflow_execute_end(
    spec: Any,
    success: bool,
    message: str,
    config: Optional[SystemConfig] = None,
) -> None:
    """
    在 handler 返回后或异常捕获后调用。
    写入 task_steps orchestrator_end、审计 workflow_ended；
    失败且任务仍为 running 时标记 failed；
    部分任务类型在成功时可自动置 succeeded（见代码内注释）。
    """
    cfg = config or get_config()
    task_id = spec.parameters.get("task_id")
    if not task_id:
        return
    task_id = str(task_id)

    if not cfg.database.enabled or not is_database_configured(cfg):
        return

    with db_connection(cfg) as conn:
        with conn.transaction():
            row = get_task_by_task_id_in_conn(conn, task_id)
            if not row:
                return
            tu = row.id
            insert_task_step(
                conn,
                tu,
                "orchestrator_end",
                step_order=99,
                status="succeeded" if success else "failed",
                detail={"message": (message or "")[:2000]},
                error_code=None if success else "WORKFLOW_FAILED",
                error_message=None if success else (message or "")[:2000],
            )
            insert_audit_log_conn(
                conn,
                "task",
                task_id,
                "workflow_ended",
                {"success": success, "message": (message or "")[:500]},
            )
            if not success and row.status == "running":
                mark_task_failed(
                    conn,
                    tu,
                    "INTERNAL_ERROR",
                    message or "workflow failed",
                    task_id,
                )
                return
            tt = getattr(spec.task_type, "value", str(spec.task_type))
            if (
                success
                and row.status == "running"
                and tt in ("default_conversation", "document_editing")
            ):
                # 无后续 AgentC 的典型闭环：直接标成功
                mark_task_succeeded(conn, tu, task_id)

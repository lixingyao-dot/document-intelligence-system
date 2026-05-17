"""
工作流数据库持久化层
用户自定义工作流（type=custom）存 PostgreSQL；已移除系统内置模板工作流。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg.errors import DeadlockDetected
from psycopg.rows import dict_row

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured
from utils.logger import get_logger

logger = get_logger(__name__)

# 进程内只跑一次 DDL；跨进程用 PostgreSQL advisory lock 串行化，避免多 worker 启动时死锁。
_WORKFLOW_SCHEMA_LOCK = threading.Lock()
_WORKFLOW_SCHEMA_READY = False
_WORKFLOW_SCHEMA_ADVISORY_KEY = 0x57465321  # 'WFS!'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 公共检查
# ---------------------------------------------------------------------------


def is_db_enabled(config: Optional[SystemConfig] = None) -> bool:
    from utils.desktop_runtime import is_desktop_app

    if is_desktop_app():
        return False
    cfg = config or get_config()
    return cfg.database.enabled and is_database_configured(cfg)


def _run_workflow_schema_ddl(cur) -> None:
    """在工作流表上执行一次性 DDL（须在 advisory lock 内调用）。"""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_workflows (
            workflow_id VARCHAR(64) PRIMARY KEY,
            name         VARCHAR(255) NOT NULL DEFAULT '未命名',
            icon         VARCHAR(32)  NOT NULL DEFAULT '🔧',
            type         VARCHAR(16)  NOT NULL DEFAULT 'custom',
            nodes        JSONB        NOT NULL DEFAULT '[]',
            config       JSONB        NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_updated ON user_workflows(updated_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_type ON user_workflows(type)"
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_executions (
            execution_id        VARCHAR(64) PRIMARY KEY,
            status              VARCHAR(32) NOT NULL DEFAULT 'running',
            error_code          VARCHAR(64),
            progress            INT         NOT NULL DEFAULT 0,
            current_file_index  INT         NOT NULL DEFAULT 0,
            total_files         INT         NOT NULL DEFAULT 0,
            current_file_name   TEXT        NOT NULL DEFAULT '',
            logs                JSONB       NOT NULL DEFAULT '[]',
            output_files        JSONB       NOT NULL DEFAULT '[]',
            error               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_exec_updated ON workflow_executions(updated_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_exec_status ON workflow_executions(status)"
    )
    cur.execute(
        "ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS error_code VARCHAR(64)"
    )


def _ensure_workflow_tables(conn) -> None:
    """确保工作流相关表存在（进程内缓存 + 跨进程 advisory lock）。"""
    global _WORKFLOW_SCHEMA_READY
    if _WORKFLOW_SCHEMA_READY:
        return
    with _WORKFLOW_SCHEMA_LOCK:
        if _WORKFLOW_SCHEMA_READY:
            return
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_lock(%s)", (_WORKFLOW_SCHEMA_ADVISORY_KEY,))
                    try:
                        _run_workflow_schema_ddl(cur)
                    finally:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (_WORKFLOW_SCHEMA_ADVISORY_KEY,))
                _WORKFLOW_SCHEMA_READY = True
                return
            except DeadlockDetected as exc:
                last_exc = exc
                logger.warning(
                    "[workflow_repo] schema DDL deadlock (attempt %s/4), retrying: %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(0.15 * (attempt + 1))
        if last_exc is not None:
            raise last_exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def db_list_workflows(config: Optional[SystemConfig] = None) -> List[Dict[str, Any]]:
    """
    获取所有用户自定义工作流摘要（不含完整 nodes），按更新时间倒序。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return []

    try:
        with db_connection(cfg) as conn:
            _ensure_workflow_tables(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT workflow_id, name, icon, type,
                           created_at, updated_at
                    FROM   user_workflows
                    WHERE  type = 'custom'
                    ORDER BY updated_at DESC
                    """,
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": str(r["workflow_id"]),
                        "name": r["name"],
                        "icon": r["icon"],
                        "type": r["type"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"[workflow_repo] db_list_workflows error: {e}")
        return []


def db_get_workflow(workflow_id: str, config: Optional[SystemConfig] = None) -> Optional[Dict[str, Any]]:
    """
    获取指定工作流的完整配置（含 nodes、config）。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return None

    try:
        with db_connection(cfg) as conn:
            _ensure_workflow_tables(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT workflow_id, name, icon, type, nodes, config,
                           created_at, updated_at
                    FROM   user_workflows
                    WHERE  workflow_id = %s AND type = 'custom'
                    """,
                    (workflow_id,),
                )
                r = cur.fetchone()
                if not r:
                    return None
                return {
                    "id": str(r["workflow_id"]),
                    "name": r["name"],
                    "icon": r["icon"],
                    "type": r["type"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    "nodes": r["nodes"] if isinstance(r["nodes"], list) else json.loads(r["nodes"] or "[]"),
                    "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"] or "{}"),
                }
    except Exception as e:
        logger.error(f"[workflow_repo] db_get_workflow({workflow_id}) error: {e}")
        return None


def db_save_workflow(
    workflow_id: str,
    name: str,
    icon: str = "🔧",
    nodes: Optional[List[Dict[str, Any]]] = None,
    config_data: Optional[Dict[str, Any]] = None,
    config: Optional[SystemConfig] = None,
) -> Dict[str, Any]:
    """
    新建或更新用户工作流。

    新建时 INSERT，返回 created_at。
    更新时 UPDATE，保留 created_at，更新 updated_at。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        raise RuntimeError("数据库未启用，无法保存工作流")

    now = _utc_now()
    nodes_json = json.dumps(nodes or [], ensure_ascii=False)
    config_json = json.dumps(config_data or {}, ensure_ascii=False)

    with db_connection(cfg) as conn:
        _ensure_workflow_tables(conn)
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                # 先查是否存在
                cur.execute(
                    "SELECT created_at FROM user_workflows WHERE workflow_id = %s",
                    (workflow_id,),
                )
                existing = cur.fetchone()
                created_at = existing["created_at"] if existing else now

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO user_workflows
                        (workflow_id, name, icon, type, nodes, config, created_at, updated_at)
                    VALUES (%s, %s, %s, 'custom', %s, %s, %s, %s)
                    ON CONFLICT (workflow_id)
                    DO UPDATE SET
                        name       = EXCLUDED.name,
                        icon       = EXCLUDED.icon,
                        nodes      = EXCLUDED.nodes,
                        config     = EXCLUDED.config,
                        updated_at = EXCLUDED.updated_at
                    RETURNING workflow_id, name, icon, type, nodes, config, created_at, updated_at
                    """,
                    (workflow_id, name, icon, nodes_json, config_json, created_at, now),
                )
                r = cur.fetchone()
                logger.info(f"[workflow_repo] 工作流已保存: {workflow_id} ({name})")
                return {
                    "id": str(r["workflow_id"]),
                    "name": r["name"],
                    "icon": r["icon"],
                    "type": r["type"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    "nodes": r["nodes"] if isinstance(r["nodes"], list) else json.loads(r["nodes"] or "[]"),
                    "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"] or "{}"),
                }


def db_delete_workflow(workflow_id: str, config: Optional[SystemConfig] = None) -> bool:
    """
    删除指定工作流，返回 True 成功，False 不存在。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return False

    try:
        with db_connection(cfg) as conn:
            _ensure_workflow_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_workflows WHERE workflow_id = %s AND type = 'custom'",
                    (workflow_id,),
                )
                deleted = cur.rowcount > 0
                if deleted:
                    logger.info(f"[workflow_repo] 工作流已删除: {workflow_id}")
                return deleted
    except Exception as e:
        logger.error(f"[workflow_repo] db_delete_workflow({workflow_id}) error: {e}")
        return False


# ---------------------------------------------------------------------------
# workflow_executions
# ---------------------------------------------------------------------------


def db_load_execution_states(config: Optional[SystemConfig] = None) -> Dict[str, Dict[str, Any]]:
    """加载工作流执行状态（按 execution_id 索引）。"""
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return {}
    try:
        with db_connection(cfg) as conn:
            _ensure_workflow_tables(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT execution_id, status, error_code, progress, current_file_index, total_files,
                           current_file_name, logs, output_files, error, created_at, updated_at
                    FROM workflow_executions
                    ORDER BY updated_at DESC
                    """
                )
                rows = cur.fetchall()
                result: Dict[str, Dict[str, Any]] = {}
                for r in rows:
                    execution_id = str(r["execution_id"])
                    result[execution_id] = {
                        "status": r["status"],
                        "error_code": r["error_code"],
                        "progress": int(r["progress"] or 0),
                        "current_file_index": int(r["current_file_index"] or 0),
                        "total_files": int(r["total_files"] or 0),
                        "current_file_name": r["current_file_name"] or "",
                        "logs": r["logs"] if isinstance(r["logs"], list) else json.loads(r["logs"] or "[]"),
                        "output_files": r["output_files"] if isinstance(r["output_files"], list) else json.loads(r["output_files"] or "[]"),
                        "error": r["error"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    }
                return result
    except Exception as exc:
        logger.error(f"[workflow_repo] db_load_execution_states error: {exc}")
        return {}


def db_save_execution_states(
    states: Dict[str, Dict[str, Any]],
    config: Optional[SystemConfig] = None,
) -> bool:
    """批量保存执行状态（全量 upsert）。"""
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return False
    try:
        with db_connection(cfg) as conn:
            _ensure_workflow_tables(conn)
            with conn.transaction():
                with conn.cursor() as cur:
                    for execution_id, s in states.items():
                        if not isinstance(s, dict):
                            continue
                        cur.execute(
                            """
                            INSERT INTO workflow_executions
                                (execution_id, status, error_code, progress, current_file_index, total_files,
                                 current_file_name, logs, output_files, error, created_at, updated_at)
                            VALUES
                                (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                            ON CONFLICT (execution_id)
                            DO UPDATE SET
                                status = EXCLUDED.status,
                                error_code = EXCLUDED.error_code,
                                progress = EXCLUDED.progress,
                                current_file_index = EXCLUDED.current_file_index,
                                total_files = EXCLUDED.total_files,
                                current_file_name = EXCLUDED.current_file_name,
                                logs = EXCLUDED.logs,
                                output_files = EXCLUDED.output_files,
                                error = EXCLUDED.error,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                str(execution_id),
                                str(s.get("status") or "running"),
                                s.get("error_code"),
                                int(s.get("progress") or 0),
                                int(s.get("current_file_index") or 0),
                                int(s.get("total_files") or 0),
                                str(s.get("current_file_name") or ""),
                                json.dumps(s.get("logs") or [], ensure_ascii=False),
                                json.dumps(s.get("output_files") or [], ensure_ascii=False),
                                s.get("error"),
                                s.get("created_at") or _utc_now(),
                                s.get("updated_at") or _utc_now(),
                            ),
                        )
        return True
    except Exception as exc:
        logger.error(f"[workflow_repo] db_save_execution_states error: {exc}")
        return False

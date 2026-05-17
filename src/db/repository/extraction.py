"""抽取 JSON 入库与 resolve_task_id。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from config import SystemConfig, get_config
from db.connection import db_connection

from .audit import insert_task_step
from .mutations import (
    ensure_task,
    mark_task_failed,
    mark_task_succeeded,
    save_extraction_result,
)
from .types import SaveExtractionOutcome


def resolve_task_id(parameters: Dict[str, Any], session_id: Optional[str]) -> str:
    """从 parameters.data、parameters.task_id 或 session 解析业务 task_id。"""
    data = parameters.get("data")
    if isinstance(data, dict) and data.get("task_id"):
        return str(data["task_id"])
    if parameters.get("task_id"):
        return str(parameters["task_id"])
    if session_id:
        return str(session_id)
    return uuid.uuid4().hex[:12]


def save_extraction_from_agent_payload(
    parameters: Dict[str, Any],
    task_type: str,
    session_id: Optional[str],
    config: Optional[SystemConfig] = None,
) -> SaveExtractionOutcome:
    """将 Agent 传入的 parameters 写入 tasks + extraction_results。"""
    cfg = config or get_config()
    data = parameters.get("data")
    if not isinstance(data, dict):
        raise ValueError("parameters.data 必须为对象（dict）")

    task_id = resolve_task_id(parameters, session_id)
    sv = str(data.get("schema_version") or parameters.get("schema_version") or "1.0.0")
    payload = dict(data)
    if "task_id" not in payload:
        payload["task_id"] = task_id

    if "fields" not in payload:
        raise ValueError("抽取 JSON 缺少 fields（契约 v1）")

    with db_connection(cfg) as conn:
        with conn.transaction():
            tu = ensure_task(conn, task_id, task_type, metadata={"session_id": session_id})
            insert_task_step(
                conn,
                tu,
                "parse_doc",
                step_order=0,
                status="skipped",
                detail={"reason": "extraction_payload_ready"},
            )
            ext_id, ver = save_extraction_result(conn, tu, sv, payload)
            insert_task_step(
                conn,
                tu,
                "save_result",
                step_order=1,
                status="succeeded",
                detail={"extraction_id": ext_id, "result_version": ver},
            )
            mark_task_succeeded(conn, tu, task_id)
            return SaveExtractionOutcome(
                task_id=task_id,
                task_uuid=tu,
                extraction_id=ext_id,
                result_version=ver,
            )


def save_extraction_from_agent_payload_safe(
    parameters: Dict[str, Any],
    task_type: str,
    session_id: Optional[str],
    config: Optional[SystemConfig] = None,
) -> Tuple[bool, Optional[SaveExtractionOutcome], str]:
    """包装事务：成功 (True, outcome, '')；失败 (False, None, message)。"""
    cfg = config or get_config()
    try:
        out = save_extraction_from_agent_payload(parameters, task_type, session_id, cfg)
        return True, out, ""
    except ValueError as e:
        return False, None, str(e)
    except Exception as e:
        try:
            tid = resolve_task_id(parameters, session_id)
            with db_connection(cfg) as conn:
                with conn.transaction():
                    tu = ensure_task(conn, tid, task_type, {})
                    insert_task_step(
                        conn,
                        tu,
                        "save_result",
                        step_order=0,
                        status="failed",
                        error_code="INTERNAL_ERROR",
                        error_message=str(e)[:2000],
                        detail={},
                    )
                    mark_task_failed(conn, tu, "INTERNAL_ERROR", str(e), tid)
        except Exception:
            pass
        return False, None, str(e)

"""填表报告、执行日志、文档元数据写入。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from psycopg.types.json import Json

from config import SystemConfig, get_config
from db.connection import db_connection


def insert_fill_report(
    task_uuid: str,
    payload: Dict[str, Any],
    config: Optional[SystemConfig] = None,
) -> str:
    """填表报告入库。"""
    if "schema_version" not in payload or "output_file" not in payload:
        raise ValueError("payload 须包含 schema_version 与 output_file")
    cfg = config or get_config()
    filled = payload.get("filled_fields", [])
    skipped = payload.get("skipped_fields", [])
    warnings = payload.get("warnings", [])
    errors = payload.get("errors", [])
    if not isinstance(filled, list):
        filled = []
    if not isinstance(skipped, list):
        skipped = []
    if not isinstance(warnings, list):
        warnings = []
    if not isinstance(errors, list):
        errors = []
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fill_reports (
                        task_uuid, schema_version, template_id, output_file,
                        filled_fields, skipped_fields, warnings, errors
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    RETURNING id::text
                    """,
                    (
                        task_uuid,
                        str(payload["schema_version"]),
                        payload.get("template_id"),
                        Json(payload["output_file"]),
                        Json(filled),
                        Json(skipped),
                        Json(warnings),
                        Json(errors),
                    ),
                )
                return str(cur.fetchone()[0])


def insert_agent_log(
    task_uuid: str,
    payload: Dict[str, Any],
    config: Optional[SystemConfig] = None,
) -> str:
    """执行日志入库。"""
    if "action" not in payload or "summary" not in payload:
        raise ValueError("payload 须包含 action 与 summary")
    cfg = config or get_config()
    extras = payload.get("extras") or {}
    if not isinstance(extras, dict):
        extras = {}
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_execution_logs (
                        task_uuid, action, summary, ops_count, rollback_id, detail_ref, extras
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id::text
                    """,
                    (
                        task_uuid,
                        str(payload["action"]),
                        str(payload["summary"]),
                        payload.get("ops_count"),
                        payload.get("rollback_id"),
                        payload.get("detail_ref"),
                        Json(extras),
                    ),
                )
                return str(cur.fetchone()[0])


def insert_document_asset(
    task_uuid: str,
    payload: Dict[str, Any],
    config: Optional[SystemConfig] = None,
) -> str:
    """文档元数据入库。"""
    role = str(payload.get("role") or "source")
    if role not in ("source", "template", "output", "aux"):
        raise ValueError("role 须为 source | template | output | aux")
    cfg = config or get_config()
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO document_assets (
                        task_uuid, role, storage_key, local_path, file_name, file_hash,
                        mime_type, byte_size, page_count, metadata
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    RETURNING id::text
                    """,
                    (
                        task_uuid,
                        role,
                        payload.get("storage_key"),
                        payload.get("local_path"),
                        payload.get("file_name"),
                        payload.get("file_hash"),
                        payload.get("mime_type"),
                        payload.get("byte_size"),
                        payload.get("page_count"),
                        Json(meta),
                    ),
                )
                return str(cur.fetchone()[0])

"""会话、消息和文件的数据访问层。

数据库启用时优先使用 PostgreSQL；否则退回内存存储，便于本地演示和测试。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from psycopg.rows import dict_row
from psycopg.types.json import Json

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured
from utils.datetime_util import utc_iso

from .memory_store import (
    add_message as memory_add_message,
    add_session_file as memory_add_session_file,
    create_session as memory_create_session,
    delete_session as memory_delete_session,
    delete_session_file as memory_delete_session_file,
    get_messages as memory_get_messages,
    get_session_by_id as memory_get_session_by_id,
    get_session_files as memory_get_session_files,
    get_session_with_messages as memory_get_session_with_messages,
    list_sessions as memory_list_sessions,
    update_file_selection as memory_update_file_selection,
    update_session as memory_update_session,
)
from .models import FileRow, MessageRow, SessionListItem, SessionRow, SessionWithMessages


def _db_enabled(config: Optional[SystemConfig] = None) -> bool:
    cfg = config or get_config()
    return cfg.database.enabled and is_database_configured(cfg)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_session(row) -> SessionRow:
    return SessionRow(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        title=str(row["title"]),
        current_mode=str(row["current_mode"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        user_id=row.get("user_id"),
    )


def _row_to_message(row) -> MessageRow:
    return MessageRow(
        id=int(row["id"]),
        session_id=int(row["session_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        metadata=row.get("metadata"),
        created_at=row["created_at"],
        user_id=row.get("user_id"),
    )


def _row_to_file(row) -> FileRow:
    return FileRow(
        id=int(row["id"]),
        session_id=int(row["session_id"]),
        file_name=str(row["file_name"]),
        file_type=str(row["file_type"]),
        file_path=str(row["file_path"]),
        file_size=int(row["file_size"]),
        is_selected=bool(row.get("is_selected", False)),
        created_at=row["created_at"],
        user_id=row.get("user_id"),
        source=str(row.get("source") or "upload"),
        role=str(row.get("role") or "source"),
        task_uuid=row.get("task_uuid"),
        origin_file_id=row.get("origin_file_id"),
        storage_key=row.get("storage_key"),
        mime_type=row.get("mime_type"),
        file_hash=row.get("file_hash"),
        deleted_at=row.get("deleted_at"),
    )


def create_session(
    title: str = "新会话",
    current_mode: str = "default_conversation",
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> SessionRow:
    if not _db_enabled(config):
        return memory_create_session(title=title, current_mode=current_mode, config=config, user_id=user_id)

    cfg = config or get_config()
    session_id = str(uuid.uuid4())
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (session_id, title, current_mode, user_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::uuid, %s, %s)
                    RETURNING id, session_id, title, current_mode, created_at, updated_at, user_id
                    """,
                    (session_id, title, current_mode, user_id, now, now),
                )
                return _row_to_session(cur.fetchone())


def get_session_by_id(
    session_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[SessionRow]:
    if not _db_enabled(config):
        return memory_get_session_by_id(session_id, config=config)

    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT id, session_id, title, current_mode, created_at, updated_at, user_id
                    FROM sessions
                    WHERE session_id = %s AND user_id = %s::uuid
                    """,
                    (session_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT id, session_id, title, current_mode, created_at, updated_at, user_id
                    FROM sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
            row = cur.fetchone()
            return _row_to_session(row) if row else None


def list_sessions(
    limit: int = 50,
    offset: int = 0,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> tuple:
    if not _db_enabled(config):
        return memory_list_sessions(limit=limit, offset=offset, config=config)

    cfg = config or get_config()
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT COUNT(*)::bigint AS c
                    FROM sessions
                    WHERE user_id = %s::uuid
                    """,
                    (user_id,),
                )
            else:
                cur.execute("SELECT COUNT(*)::bigint AS c FROM sessions")
            total = int(cur.fetchone()["c"])

        with conn.cursor(row_factory=dict_row) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT s.id, s.session_id, s.title, s.current_mode, s.created_at, s.updated_at, s.user_id,
                           COALESCE(m.message_count, 0) AS message_count
                    FROM sessions s
                    LEFT JOIN (
                        SELECT session_id, COUNT(*) AS message_count
                        FROM messages
                        GROUP BY session_id
                    ) m ON m.session_id = s.id
                    WHERE s.user_id = %s::uuid
                    ORDER BY s.updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, lim, off),
                )
            else:
                cur.execute(
                    """
                    SELECT s.id, s.session_id, s.title, s.current_mode, s.created_at, s.updated_at, s.user_id,
                           COALESCE(m.message_count, 0) AS message_count
                    FROM sessions s
                    LEFT JOIN (
                        SELECT session_id, COUNT(*) AS message_count
                        FROM messages
                        GROUP BY session_id
                    ) m ON m.session_id = s.id
                    ORDER BY s.updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (lim, off),
                )
            rows = cur.fetchall()

    items = [
        SessionListItem(
            session_id=str(row["session_id"]),
            title=str(row["title"]),
            current_mode=str(row["current_mode"]),
            message_count=int(row.get("message_count", 0)),
            created_at=utc_iso(row.get("created_at")),
            updated_at=utc_iso(row.get("updated_at")),
        )
        for row in rows
    ]
    return items, total


def update_session(
    session_id: str,
    title: Optional[str] = None,
    current_mode: Optional[str] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[SessionRow]:
    if not _db_enabled(config):
        return memory_update_session(session_id, title=title, current_mode=current_mode, config=config)

    cfg = config or get_config()
    if title is None and current_mode is None:
        return get_session_by_id(session_id, cfg, user_id=user_id)
    set_clauses = []
    params: List[Any] = []
    if title is not None:
        set_clauses.append("title = %s")
        params.append(title)
    if current_mode is not None:
        set_clauses.append("current_mode = %s")
        params.append(current_mode)
    set_clauses.append("updated_at = %s")
    params.append(_utc_now())

    where_sql = "session_id = %s"
    params.append(session_id)
    if user_id:
        where_sql += " AND user_id = %s::uuid"
        params.append(user_id)

    sql = f"UPDATE sessions SET {', '.join(set_clauses)} WHERE {where_sql} RETURNING id, session_id, title, current_mode, created_at, updated_at, user_id"
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _row_to_session(row) if row else None


def delete_session(
    session_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    if not _db_enabled(config):
        return memory_delete_session(session_id, config=config)

    cfg = config or get_config()
    params: List[Any] = [session_id]
    where_sql = "session_id = %s"
    if user_id:
        where_sql += " AND user_id = %s::uuid"
        params.append(user_id)
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM sessions WHERE {where_sql}", tuple(params))
                return cur.rowcount > 0


def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> MessageRow:
    if not _db_enabled(config):
        return memory_add_message(session_id, role, content, metadata=metadata, config=config, user_id=user_id)

    cfg = config or get_config()
    session = get_session_by_id(session_id, cfg, user_id=user_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO messages (session_id, user_id, role, content, metadata, created_at)
                    VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
                    RETURNING id, session_id, user_id, role, content, metadata, created_at
                    """,
                    (session.id, user_id or session.user_id, role, content, Json(metadata or {}), now),
                )
                row = cur.fetchone()
                with conn.cursor() as cur2:
                    cur2.execute(
                        "UPDATE sessions SET updated_at = %s WHERE id = %s",
                        (now, session.id),
                    )
                return _row_to_message(row)


def get_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> List[MessageRow]:
    if not _db_enabled(config):
        return memory_get_messages(session_id, limit=limit, offset=offset, config=config)

    cfg = config or get_config()
    session = get_session_by_id(session_id, cfg, user_id=user_id)
    if not session:
        return []
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT id, session_id, user_id, role, content, metadata, created_at
                    FROM messages
                    WHERE session_id = %s AND user_id = %s::uuid
                    ORDER BY created_at ASC, id ASC
                    LIMIT %s OFFSET %s
                    """,
                    (session.id, user_id, lim, off),
                )
            else:
                cur.execute(
                    """
                    SELECT id, session_id, user_id, role, content, metadata, created_at
                    FROM messages
                    WHERE session_id = %s
                    ORDER BY created_at ASC, id ASC
                    LIMIT %s OFFSET %s
                    """,
                    (session.id, lim, off),
                )
            rows = cur.fetchall()
    return [_row_to_message(row) for row in rows]


def get_session_with_messages(
    session_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[SessionWithMessages]:
    session = get_session_by_id(session_id, config, user_id=user_id)
    if not session:
        return None
    messages = get_messages(session_id, config=config, user_id=user_id)
    return SessionWithMessages(session=session, messages=messages)


def add_session_file(
    session_id: str,
    file_name: str,
    file_type: str,
    file_path: str,
    file_size: int,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
    source: str = "upload",
    role: str = "source",
    task_uuid: Optional[str] = None,
    origin_file_id: Optional[int] = None,
    storage_key: Optional[str] = None,
    mime_type: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> FileRow:
    if not _db_enabled(config):
        return memory_add_session_file(
            session_id,
            file_name,
            file_type,
            file_path,
            file_size,
            config=config,
            user_id=user_id,
            source=source,
            role=role,
            task_uuid=task_uuid,
            origin_file_id=origin_file_id,
            storage_key=storage_key,
            mime_type=mime_type,
            file_hash=file_hash,
        )

    cfg = config or get_config()
    session = get_session_by_id(session_id, cfg, user_id=user_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO session_files (
                        session_id, user_id, file_name, file_type, file_path, file_size,
                        is_selected, source, role, task_uuid, origin_file_id, storage_key,
                        mime_type, file_hash, created_at
                    )
                    VALUES (
                        %s, %s::uuid, %s, %s, %s, %s,
                        FALSE, %s, %s, %s::uuid, %s, %s, %s, %s, %s
                    )
                    RETURNING id, session_id, user_id, file_name, file_type, file_path, file_size,
                              is_selected, created_at, source, role, task_uuid, origin_file_id,
                              storage_key, mime_type, file_hash, deleted_at
                    """,
                    (
                        session.id,
                        user_id or session.user_id,
                        file_name,
                        file_type,
                        file_path,
                        file_size,
                        source,
                        role,
                        task_uuid,
                        origin_file_id,
                        storage_key,
                        mime_type,
                        file_hash,
                        now,
                    ),
                )
                return _row_to_file(cur.fetchone())


def get_session_files(
    session_id: str,
    file_type: Optional[str] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> List[FileRow]:
    if not _db_enabled(config):
        return memory_get_session_files(session_id, file_type=file_type, config=config)

    cfg = config or get_config()
    session = get_session_by_id(session_id, cfg, user_id=user_id)
    if not session:
        return []
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if file_type:
                cur.execute(
                    """
                    SELECT id, session_id, user_id, file_name, file_type, file_path, file_size,
                           is_selected, created_at, source, role, task_uuid, origin_file_id,
                           storage_key, mime_type, file_hash, deleted_at
                    FROM session_files
                    WHERE session_id = %s AND file_type = %s AND deleted_at IS NULL
                    ORDER BY created_at DESC, id DESC
                    """,
                    (session.id, file_type),
                )
            else:
                cur.execute(
                    """
                    SELECT id, session_id, user_id, file_name, file_type, file_path, file_size,
                           is_selected, created_at, source, role, task_uuid, origin_file_id,
                           storage_key, mime_type, file_hash, deleted_at
                    FROM session_files
                    WHERE session_id = %s AND deleted_at IS NULL
                    ORDER BY created_at DESC, id DESC
                    """,
                    (session.id,),
                )
            rows = cur.fetchall()
    return [_row_to_file(row) for row in rows]


def update_file_selection(
    file_id: int,
    is_selected: bool,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    if not _db_enabled(config):
        return memory_update_file_selection(file_id, is_selected, config=config)

    cfg = config or get_config()
    params: List[Any] = [is_selected, _utc_now(), file_id]
    where_sql = "id = %s"
    if user_id:
        where_sql += " AND user_id = %s::uuid"
        params.append(user_id)
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE session_files SET is_selected = %s, updated_at = %s WHERE {where_sql}",
                    tuple(params),
                )
                return cur.rowcount > 0


def delete_session_file(
    file_id: int,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    if not _db_enabled(config):
        return memory_delete_session_file(file_id, config=config)

    cfg = config or get_config()
    params: List[Any] = [file_id]
    where_sql = "id = %s"
    if user_id:
        where_sql += " AND user_id = %s::uuid"
        params.append(user_id)
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE session_files SET deleted_at = %s, is_selected = FALSE WHERE {where_sql}",
                    tuple([_utc_now()] + params),
                )
                return cur.rowcount > 0


__all__ = [
    "create_session",
    "get_session_by_id",
    "list_sessions",
    "update_session",
    "delete_session",
    "add_message",
    "get_messages",
    "get_session_with_messages",
    "add_session_file",
    "get_session_files",
    "update_file_selection",
    "delete_session_file",
]

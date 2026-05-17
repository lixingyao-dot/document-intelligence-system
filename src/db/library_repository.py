"""文档库数据访问层（文档空间 & 文档，基于 library_documents 表）"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured


# ---------------------------------------------------------------------------
# 数据模型（对外 API 保持原有字段名，内部映射到 library_documents）
# ---------------------------------------------------------------------------

@dataclass
class LibrarySpaceRow:
    id: str
    user_id: Optional[str]
    name: str
    icon: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    doc_count: int = 0


@dataclass
class LibraryDocRow:
    id: str
    space_id: str
    user_id: Optional[str]
    file_name: str
    file_size: int
    mime_type: Optional[str]
    file_extension: Optional[str]
    storage_key: Optional[str]
    blob_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _db_enabled(config: Optional[SystemConfig] = None) -> bool:
    from utils.desktop_runtime import is_desktop_app

    if is_desktop_app():
        return False
    cfg = config or get_config()
    return cfg.database.enabled and is_database_configured(cfg)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_space(row: Dict[str, Any]) -> LibrarySpaceRow:
    return LibrarySpaceRow(
        id=str(row["id"]),
        user_id=row.get("user_id"),
        name=str(row["name"]),
        icon=str(row.get("icon", "📁")),
        description=row.get("description"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        doc_count=int(row.get("doc_count", 0)),
    )


def _row_to_doc(row: Dict[str, Any]) -> LibraryDocRow:
    return LibraryDocRow(
        id=str(row["id"]),
        space_id=str(row.get("space_id", "")),
        user_id=row.get("user_id"),
        file_name=str(row.get("file_name", "")),
        file_size=int(row.get("file_size", 0)),
        mime_type=row.get("mime_type"),
        file_extension=row.get("file_extension"),
        storage_key=row.get("storage_key"),
        blob_url=row.get("blob_url"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at") or row["created_at"],
        deleted_at=row.get("deleted_at"),
    )


# ---------------------------------------------------------------------------
# 空间 CRUD
# ---------------------------------------------------------------------------

def create_library_space(
    name: str,
    icon: str = "📁",
    description: Optional[str] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> LibrarySpaceRow:
    """创建文档空间"""
    cfg = config or get_config()
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO document_spaces (user_id, name, icon, description, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, user_id, name, icon, description, created_at, updated_at
                    """,
                    (user_id, name, icon, description, now, now),
                )
                return _row_to_space(cur.fetchone())


def get_library_space_by_id(
    space_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[LibrarySpaceRow]:
    """按 ID 获取空间"""
    cfg = config or get_config()
    params: List[Any] = [space_id]
    where_sql = "id = %s"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT s.id, s.user_id, s.name, s.icon, s.description,
                       s.created_at, s.updated_at,
                       COALESCE(d.doc_count, 0) AS doc_count
                FROM document_spaces s
                LEFT JOIN (
                    SELECT space_id, COUNT(*) AS doc_count
                    FROM library_documents
                    WHERE deleted_at IS NULL
                    GROUP BY space_id
                ) d ON d.space_id = s.id
                WHERE {where_sql}
                """,
                tuple(params),
            )
            row = cur.fetchone()
            return _row_to_space(row) if row else None


def get_library_spaces(
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> List[LibrarySpaceRow]:
    """获取用户所有文档空间"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT s.id, s.user_id, s.name, s.icon, s.description,
                           s.created_at, s.updated_at,
                           COALESCE(d.doc_count, 0) AS doc_count
                    FROM document_spaces s
                    LEFT JOIN (
                        SELECT space_id, COUNT(*) AS doc_count
                        FROM library_documents
                        WHERE deleted_at IS NULL
                        GROUP BY space_id
                    ) d ON d.space_id = s.id
                    WHERE s.user_id = %s
                    ORDER BY s.created_at DESC
                    """,
                    (user_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT s.id, s.user_id, s.name, s.icon, s.description,
                           s.created_at, s.updated_at,
                           COALESCE(d.doc_count, 0) AS doc_count
                    FROM document_spaces s
                    LEFT JOIN (
                        SELECT space_id, COUNT(*) AS doc_count
                        FROM library_documents
                        WHERE deleted_at IS NULL
                        GROUP BY space_id
                    ) d ON d.space_id = s.id
                    ORDER BY s.created_at DESC
                    """
                )
            return [_row_to_space(row) for row in cur.fetchall()]


def update_library_space(
    space_id: str,
    name: Optional[str] = None,
    icon: Optional[str] = None,
    description: Optional[str] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[LibrarySpaceRow]:
    """更新文档空间"""
    cfg = config or get_config()
    set_clauses = []
    params: List[Any] = []
    if name is not None:
        set_clauses.append("name = %s")
        params.append(name)
    if icon is not None:
        set_clauses.append("icon = %s")
        params.append(icon)
    if description is not None:
        set_clauses.append("description = %s")
        params.append(description)

    if not set_clauses:
        return get_library_space_by_id(space_id, cfg, user_id=user_id)

    set_clauses.append("updated_at = %s")
    params.append(_utc_now())

    where_sql = "id = %s"
    params.append(space_id)
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    UPDATE document_spaces SET {', '.join(set_clauses)}
                    WHERE {where_sql}
                    RETURNING id, user_id, name, icon, description, created_at, updated_at
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _row_to_space(row)
                result.doc_count = _get_doc_count(cfg, space_id)
                return result


def delete_library_space(
    space_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    """删除文档空间（级联软删除文档）"""
    cfg = config or get_config()
    params: List[Any] = [space_id]
    where_sql = "id = %s"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.transaction():
            # 软删除空间下所有文档
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE library_documents SET deleted_at = %s WHERE space_id = %s AND deleted_at IS NULL",
                    (_utc_now(), space_id),
                )
            # 删除空间
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM document_spaces WHERE {where_sql}", tuple(params))
                return cur.rowcount > 0


def _get_doc_count(config: SystemConfig, space_id: str) -> int:
    with db_connection(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS doc_count
                FROM library_documents
                WHERE space_id = %s AND deleted_at IS NULL
                """,
                (space_id,),
            )
            return cur.fetchone()["doc_count"]


# ---------------------------------------------------------------------------
# 文档 CRUD
# ---------------------------------------------------------------------------

def add_library_doc(
    space_id: str,
    file_name: str,
    file_size: int,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    storage_key: Optional[str] = None,
    blob_url: Optional[str] = None,
) -> LibraryDocRow:
    """添加文档到空间"""
    cfg = config or get_config()
    now = _utc_now()
    file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else None

    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO library_documents (
                        space_id, user_id, file_name, mime_type,
                        file_size, storage_key, blob_url,
                        file_extension, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, space_id, user_id, file_name, mime_type,
                              file_size, storage_key, blob_url,
                              file_extension, created_at, updated_at, deleted_at
                    """,
                    (
                        space_id, user_id, file_name, mime_type,
                        file_size, storage_key, blob_url,
                        file_ext, now, now,
                    ),
                )
                return _row_to_doc(cur.fetchone())


def get_library_docs(
    space_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> List[LibraryDocRow]:
    """获取空间下所有未删除文档"""
    cfg = config or get_config()
    params: List[Any] = [space_id]
    where_sql = "space_id = %s AND deleted_at IS NULL"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT id, space_id, user_id, file_name, mime_type,
                       file_size, storage_key, blob_url,
                       file_extension, created_at, updated_at, deleted_at
                FROM library_documents
                WHERE {where_sql}
                ORDER BY created_at DESC
                """,
                tuple(params),
            )
            return [_row_to_doc(row) for row in cur.fetchall()]


def get_library_doc_by_id(
    doc_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[LibraryDocRow]:
    """按 ID 获取文档"""
    cfg = config or get_config()
    if not _db_enabled(cfg):
        return None
    params: List[Any] = [doc_id]
    where_sql = "id = %s AND deleted_at IS NULL"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT id, space_id, user_id, file_name, mime_type,
                       file_size, storage_key, blob_url,
                       file_extension, created_at, updated_at, deleted_at
                FROM library_documents
                WHERE {where_sql}
                """,
                tuple(params),
            )
            row = cur.fetchone()
            return _row_to_doc(row) if row else None


def update_library_doc(
    doc_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[LibraryDocRow]:
    """更新文档（预留）"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE library_documents SET updated_at = %s
                    WHERE id = %s AND deleted_at IS NULL
                    RETURNING id, space_id, user_id, file_name, mime_type,
                              file_size, storage_key, blob_url,
                              file_extension, created_at, updated_at, deleted_at
                    """,
                    (_utc_now(), doc_id),
                )
                row = cur.fetchone()
                return _row_to_doc(row) if row else None


def delete_library_doc(
    doc_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    """软删除文档"""
    cfg = config or get_config()
    params: List[Any] = [_utc_now(), doc_id]
    where_sql = "id = %s"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE library_documents SET deleted_at = %s WHERE {where_sql}",
                    tuple(params),
                )
                return cur.rowcount > 0


def get_space_doc_count(
    space_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> int:
    """获取空间文档数量"""
    cfg = config or get_config()
    params: List[Any] = [space_id]
    where_sql = "space_id = %s AND deleted_at IS NULL"
    if user_id:
        where_sql += " AND user_id = %s"
        params.append(user_id)

    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)::int AS doc_count
                FROM library_documents
                WHERE {where_sql}
                """,
                tuple(params),
            )
            return cur.fetchone()["doc_count"]


__all__ = [
    "LibraryDocRow",
    "LibrarySpaceRow",
    "add_library_doc",
    "create_library_space",
    "delete_library_doc",
    "delete_library_space",
    "get_library_doc_by_id",
    "get_library_docs",
    "get_library_space_by_id",
    "get_library_spaces",
    "get_space_doc_count",
    "update_library_doc",
    "update_library_space",
]

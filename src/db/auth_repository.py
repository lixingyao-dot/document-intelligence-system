"""用户与登录会话数据库操作。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from psycopg.rows import dict_row
from psycopg.types.json import Json

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured
from db.models import AuthSessionRow, UserRow
from core.auth import access_token_from_authorization, decode_access_token, token_hash


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_user(row) -> UserRow:
    return UserRow(
        id=str(row["id"]),
        phone=str(row["phone"]),
        password_hash=str(row["password_hash"]),
        display_name=row.get("display_name"),
        status=str(row.get("status") or "active"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row.get("last_login_at"),
    )


def _row_to_auth_session(row) -> AuthSessionRow:
    return AuthSessionRow(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        token_hash=str(row["token_hash"]),
        expires_at=row["expires_at"],
        revoked_at=row.get("revoked_at"),
        created_at=row.get("created_at"),
        last_used_at=row.get("last_used_at"),
    )


def create_user(
    phone: str,
    password_hash: str,
    display_name: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> UserRow:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        raise RuntimeError("数据库未启用，无法创建用户")
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO users (phone, password_hash, display_name, status, created_at, updated_at)
                    VALUES (%s, %s, %s, 'active', %s, %s)
                    RETURNING id, phone, password_hash, display_name, status, created_at, updated_at, last_login_at
                    """,
                    (phone, password_hash, display_name, now, now),
                )
                return _row_to_user(cur.fetchone())


def get_user_by_id(user_id: str, config: Optional[SystemConfig] = None) -> Optional[UserRow]:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        return None
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, phone, password_hash, display_name, status, created_at, updated_at, last_login_at
                FROM users
                WHERE id = %s::uuid
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return _row_to_user(row) if row else None


def get_user_by_phone(phone: str, config: Optional[SystemConfig] = None) -> Optional[UserRow]:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        return None
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, phone, password_hash, display_name, status, created_at, updated_at, last_login_at
                FROM users
                WHERE phone = %s
                """,
                (phone,),
            )
            row = cur.fetchone()
            return _row_to_user(row) if row else None


def update_user_last_login(user_id: str, config: Optional[SystemConfig] = None) -> None:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        return
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET last_login_at = %s,
                        updated_at = %s
                    WHERE id = %s::uuid
                    """,
                    (now, now, user_id),
                )


def create_auth_session(
    user_id: str,
    access_token: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> AuthSessionRow:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        raise RuntimeError("数据库未启用，无法创建登录会话")
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO auth_sessions (
                        user_id, token_hash, expires_at, user_agent, ip_address, created_at, updated_at, last_used_at
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, user_id, token_hash, expires_at, revoked_at, created_at, last_used_at
                    """,
                    (
                        user_id,
                        token_hash(access_token),
                        expires_at,
                        user_agent,
                        ip_address,
                        now,
                        now,
                        now,
                    ),
                )
                return _row_to_auth_session(cur.fetchone())


def get_auth_session_by_token(access_token: str, config: Optional[SystemConfig] = None) -> Optional[AuthSessionRow]:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        return None
    with db_connection(cfg) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, token_hash, expires_at, revoked_at, created_at, last_used_at
                FROM auth_sessions
                WHERE token_hash = %s
                """,
                (token_hash(access_token),),
            )
            row = cur.fetchone()
            return _row_to_auth_session(row) if row else None


def revoke_auth_session(access_token: str, config: Optional[SystemConfig] = None) -> bool:
    cfg = config or get_config()
    if not cfg.database.enabled or not is_database_configured(cfg):
        return False
    now = _utc_now()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET revoked_at = %s,
                        updated_at = %s
                    WHERE token_hash = %s
                      AND revoked_at IS NULL
                    """,
                    (now, now, token_hash(access_token)),
                )
                return cur.rowcount > 0


def authenticate_user(phone: str, password: str, config: Optional[SystemConfig] = None) -> Optional[UserRow]:
    cfg = config or get_config()
    user = get_user_by_phone(phone, cfg)
    if not user:
        return None
    from core.auth import verify_password

    if not verify_password(password, user.password_hash):
        return None
    return user


def resolve_user_from_authorization(
    authorization: Optional[str],
    config: Optional[SystemConfig] = None,
    required: bool = False,
    allow_raw_token: bool = False,
) -> Optional[UserRow]:
    cfg = config or get_config()
    token = access_token_from_authorization(authorization, allow_raw_token=allow_raw_token)
    if not token:
        if required:
            raise PermissionError("缺少 Authorization Bearer token")
        return None
    try:
        payload = decode_access_token(token, cfg.auth.secret_key)
    except ValueError as exc:
        # 令牌格式错误、签名无效、过期等；各路由若只捕获 PermissionError 会漏掉而变成 500
        raise PermissionError(str(exc)) from exc
    user = get_user_by_id(str(payload["sub"]), cfg)
    if not user:
        raise PermissionError("用户不存在或已被禁用")
    session = get_auth_session_by_token(token, cfg)
    if not session or session.revoked_at is not None:
        raise PermissionError("登录会话已失效")
    if session.expires_at < _utc_now():
        raise PermissionError("登录会话已过期")
    # 不在每次请求时更新 last_used_at（改为后台定期更新，或仅在登录时更新一次）
    return user

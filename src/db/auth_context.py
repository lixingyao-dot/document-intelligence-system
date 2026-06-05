"""API 鉴权解析：桌面无登录；服务端启用数据库时委托 auth_repository。"""
from __future__ import annotations

from typing import Optional

from config import SystemConfig, get_config
from db.models import UserRow


def resolve_user_from_authorization(
    authorization: Optional[str],
    config: Optional[SystemConfig] = None,
    required: bool = False,
    allow_raw_token: bool = False,
) -> Optional[UserRow]:
    cfg = config or get_config()
    from utils.desktop_runtime import is_desktop_app

    if is_desktop_app() or not cfg.database.enabled:
        if required and cfg.auth.require_auth:
            if not authorization:
                raise PermissionError("需要登录")
            raise PermissionError("当前环境未启用账号登录")
        return None

    from db.auth_repository import resolve_user_from_authorization as _pg_resolve

    return _pg_resolve(
        authorization,
        config=cfg,
        required=required,
        allow_raw_token=allow_raw_token,
    )

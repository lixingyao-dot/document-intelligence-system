"""桌面 / Electron 运行时：强制本地 JSON + 文件，不连接 PostgreSQL。"""
from __future__ import annotations

import os
from typing import Any

_DESKTOP_FLAGS = ("DOC_INTEL_DESKTOP", "DOC_INTEL_ELECTRON")

_DB_ENV_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DB_URL",
    "DB_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_USERNAME",
    "DB_PASSWORD",
)


def is_desktop_app() -> bool:
    for key in _DESKTOP_FLAGS:
        if os.getenv(key, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def lock_desktop_environment() -> None:
    """刷新进程环境，避免 .env / settings 误开启数据库。"""
    if not is_desktop_app():
        return
    os.environ["DOC_INTEL_DESKTOP"] = "1"
    os.environ["DB_ENABLED"] = "false"
    os.environ["AUTH_REQUIRE_LOGIN"] = "false"
    os.environ.setdefault("STORAGE_ENABLED", "false")
    os.environ.setdefault("STORAGE_PROVIDER", "local")
    for key in _DB_ENV_KEYS:
        os.environ.pop(key, None)


def apply_desktop_config(config: Any) -> None:
    """load_config 末尾：覆盖为纯本地模式。"""
    if not is_desktop_app():
        return
    config.database.enabled = False
    config.database.url = None
    config.auth.require_auth = False
    config.storage.enabled = False
    config.storage.provider = "local"


def reload_app_config() -> None:
    try:
        from config import load_config, set_config

        set_config(load_config())
    except Exception:
        pass


def get_desktop_local_library():
    """返回 backend.local_library 模块；非桌面或未打包时 None。"""
    if not is_desktop_app():
        return None
    try:
        from backend import local_library as lib

        return lib
    except ImportError:
        return None

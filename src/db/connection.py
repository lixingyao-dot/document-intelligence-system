"""
PostgreSQL / Supabase 连接与连接池（桌面版不启用；需可选安装 psycopg）。

使用方式：
  from db.connection import get_pool, db_connection, health_check, build_conninfo
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Optional, Tuple

from config import DatabaseConfig, SystemConfig, get_config

_pool: Optional[Any] = None


def _append_sslmode_to_url(url: str, sslmode: str) -> str:
    if not sslmode or sslmode == "prefer":
        return url
    lower = url.lower()
    if "sslmode=" in lower:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode={sslmode}"


def build_conninfo(config: Optional[SystemConfig] = None) -> str:
    """生成 psycopg 可用的连接串（conninfo）。"""
    cfg = (config or get_config()).database
    if cfg.url:
        return _append_sslmode_to_url(cfg.url, cfg.sslmode)
    import psycopg

    kwargs = {
        "host": cfg.host,
        "port": cfg.port,
        "dbname": cfg.database,
        "user": cfg.username,
        "sslmode": cfg.sslmode,
    }
    if cfg.password:
        kwargs["password"] = cfg.password
    return psycopg.conninfo.make_conninfo(**kwargs)


def is_database_configured(config: Optional[SystemConfig] = None) -> bool:
    cfg = (config or get_config()).database
    if not cfg.enabled:
        return False
    if cfg.url:
        return True
    return bool(cfg.host and cfg.database and cfg.username)


def get_pool(config: Optional[SystemConfig] = None):
    """懒加载全局连接池（需在 DB_ENABLED=true 且已安装 psycopg 时调用）。"""
    global _pool
    from utils.desktop_runtime import is_desktop_app

    if is_desktop_app():
        raise RuntimeError("桌面版使用本地 JSON 存储，不连接 PostgreSQL")
    cfg = (config or get_config()).database
    if not cfg.enabled:
        raise RuntimeError("数据库未启用：请在环境变量中设置 DB_ENABLED=true")
    if not is_database_configured(config):
        raise RuntimeError(
            "数据库已启用但缺少连接信息：请设置 DATABASE_URL（或 SUPABASE_DB_URL）"
            "，或设置 DB_HOST、DB_NAME、DB_USER、DB_PASSWORD"
        )
    if _pool is None:
        from psycopg_pool import ConnectionPool

        conninfo = build_conninfo(config)
        _pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=max(1, cfg.pool_max_size),
        )
    return _pool


def reset_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def db_connection(config: Optional[SystemConfig] = None) -> Generator:
    pool = get_pool(config)
    with pool.connection() as conn:
        yield conn


def health_check(config: Optional[SystemConfig] = None) -> Tuple[bool, str]:
    cfg = (config or get_config()).database
    if not cfg.enabled:
        return False, "数据库未启用（DB_ENABLED!=true）"
    if not is_database_configured(config):
        return False, "缺少 DATABASE_URL 或 DB_HOST/DB_NAME/DB_USER 等配置"
    try:
        with db_connection(config) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True, "连接正常"
    except ImportError:
        return False, "未安装 psycopg（pip install psycopg[binary] psycopg-pool）"
    except Exception as e:
        return False, str(e)

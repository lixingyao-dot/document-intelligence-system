"""数据库连接层（桌面：memory_store + JSON；可选 PostgreSQL 需单独安装 psycopg）。"""

from .connection import (
    build_conninfo,
    db_connection,
    get_pool,
    health_check,
    is_database_configured,
    reset_pool,
)
from .models import AuthSessionRow, LibraryDocRow, LibrarySpaceRow, UserRow

__all__ = [
    "AuthSessionRow",
    "LibraryDocRow",
    "LibrarySpaceRow",
    "UserRow",
    "build_conninfo",
    "db_connection",
    "get_pool",
    "health_check",
    "is_database_configured",
    "reset_pool",
]

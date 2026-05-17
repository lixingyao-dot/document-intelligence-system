"""
一次性迁移脚本：将 JSON 文件中的工作流迁移到 PostgreSQL 数据库。
执行一次即可。
"""
import json
import sys
from pathlib import Path

# 把 src 加入路径
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import psycopg
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

from config import load_config, set_config

set_config(load_config())
from db.connection import build_conninfo, is_database_configured
from db.workflow_repository import is_db_enabled


def _create_table(conn):
    """建表（如果不存在）"""
    with conn.cursor() as cur:
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
    conn.commit()
    print("[迁移] 表 user_workflows 创建完成")


def _migrate_json(conn, json_path: Path):
    """从 JSON 文件迁移数据到数据库"""
    if not json_path.exists():
        print("[迁移] JSON 文件不存在，跳过迁移")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        print("[迁移] JSON 数据格式异常，跳过")
        return

    count = 0
    for wf_id, wf in data.items():
        nodes_json = json.dumps(wf.get("nodes") or [], ensure_ascii=False)
        config_json = json.dumps(wf.get("config") or {}, ensure_ascii=False)
        created_at = wf.get("created_at") or "NOW()"
        updated_at = wf.get("updated_at") or "NOW()"

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_workflows
                    (workflow_id, name, icon, type, nodes, config, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workflow_id) DO NOTHING
                """,
                (
                    wf_id,
                    wf.get("name", "未命名"),
                    wf.get("icon", "🔧"),
                    wf.get("type", "custom"),
                    nodes_json,
                    config_json,
                    created_at,
                    updated_at,
                ),
            )
            if cur.rowcount > 0:
                count += 1
    conn.commit()
    print(f"[迁移] 从 JSON 迁移了 {count} 条工作流到数据库")


def _verify(conn):
    """验证迁移结果"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_workflows")
        total = cur.fetchone()[0]
        cur.execute("SELECT workflow_id, name FROM user_workflows ORDER BY updated_at DESC LIMIT 5")
        rows = cur.fetchall()
    print(f"[验证] 数据库中共有 {total} 条工作流")
    for r in rows:
        print(f"  - {r[0]}: {r[1]}")


def main():
    from config import get_config

    cfg = get_config()

    print(f"数据库启用状态: {is_db_enabled(cfg)}")
    print(f"数据库地址: {cfg.database.host}/{cfg.database.database}")

    if not is_database_configured(cfg):
        print("[错误] 数据库未配置，请检查 .env 中的 DB_ENABLED 和连接信息")
        sys.exit(1)

    conninfo = build_conninfo(cfg)
    with psycopg.connect(conninfo) as conn:
        _create_table(conn)
        json_path = _SRC / "workspace" / "workflows" / "user_workflows.json"
        _migrate_json(conn, json_path)
        _verify(conn)

    print("[完成] 迁移成功！")


if __name__ == "__main__":
    main()

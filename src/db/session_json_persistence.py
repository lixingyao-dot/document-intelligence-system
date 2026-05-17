"""数据库未启用时，将会话/消息/文件持久化到 work_dir（桌面版重启不丢数据）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import SystemConfig, get_config
from db.models import FileRow, MessageRow, SessionRow
from utils.datetime_util import utc_iso


def _store_file(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    path = Path(cfg.work_dir) / "sessions" / "chat_store.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _dt_to_str(dt: Optional[datetime]) -> str:
    return utc_iso(dt)


def _str_to_dt(s: str) -> datetime:
    if not s:
        return datetime.utcnow()
    from datetime import timezone as tz

    raw = s.strip()
    if raw.endswith("Z") or raw.endswith("z"):
        raw = raw[:-1] + "+00:00"
    elif len(raw) < 11 or raw[10] not in "+-":
        raw = raw + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(tz.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return datetime.utcnow()


def serialize_memory_store(store: Any) -> Dict[str, Any]:
    sessions = []
    for s in store._sessions.values():
        sessions.append(
            {
                "id": s.id,
                "session_id": s.session_id,
                "title": s.title,
                "current_mode": s.current_mode,
                "created_at": _dt_to_str(s.created_at),
                "updated_at": _dt_to_str(s.updated_at),
                "user_id": s.user_id,
            }
        )

    messages: Dict[str, list] = {}
    for sid, msgs in store._messages.items():
        messages[str(sid)] = [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "metadata": m.metadata,
                "created_at": _dt_to_str(m.created_at),
                "user_id": m.user_id,
            }
            for m in msgs
        ]

    files: Dict[str, list] = {}
    for sid, flist in store._session_files.items():
        files[str(sid)] = [
            {
                "id": f.id,
                "session_id": f.session_id,
                "file_name": f.file_name,
                "file_type": f.file_type,
                "file_path": f.file_path,
                "file_size": f.file_size,
                "is_selected": f.is_selected,
                "created_at": _dt_to_str(f.created_at),
                "user_id": f.user_id,
                "source": f.source,
                "role": f.role,
                "task_uuid": f.task_uuid,
                "origin_file_id": f.origin_file_id,
                "storage_key": f.storage_key,
                "mime_type": f.mime_type,
                "file_hash": f.file_hash,
                "deleted_at": _dt_to_str(f.deleted_at) if f.deleted_at else None,
            }
            for f in flist
        ]

    return {
        "version": 1,
        "next_id": store._next_id,
        "sessions": sessions,
        "messages": messages,
        "files": files,
    }


def load_into_memory_store(store: Any, config: Optional[SystemConfig] = None) -> bool:
    path = _store_file(config)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False

    store._sessions.clear()
    store._sessions_by_uuid.clear()
    store._messages.clear()
    store._session_files.clear()

    store._next_id = int(data.get("next_id") or 1)

    for row in data.get("sessions") or []:
        session = SessionRow(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            title=str(row.get("title") or "新会话"),
            current_mode=str(row.get("current_mode") or "default_conversation"),
            created_at=_str_to_dt(row.get("created_at") or ""),
            updated_at=_str_to_dt(row.get("updated_at") or ""),
            user_id=row.get("user_id"),
        )
        store._sessions[session.id] = session
        store._sessions_by_uuid[session.session_id] = session
        store._messages.setdefault(session.id, [])
        store._session_files.setdefault(session.id, [])

    for sid_str, msgs in (data.get("messages") or {}).items():
        sid = int(sid_str)
        store._messages[sid] = [
            MessageRow(
                id=int(m["id"]),
                session_id=int(m["session_id"]),
                role=str(m["role"]),
                content=str(m.get("content") or ""),
                metadata=m.get("metadata"),
                created_at=_str_to_dt(m.get("created_at") or ""),
                user_id=m.get("user_id"),
            )
            for m in msgs
        ]

    for sid_str, flist in (data.get("files") or {}).items():
        sid = int(sid_str)
        store._session_files[sid] = [
            FileRow(
                id=int(f["id"]),
                session_id=int(f["session_id"]),
                file_name=str(f["file_name"]),
                file_type=str(f["file_type"]),
                file_path=str(f["file_path"]),
                file_size=int(f.get("file_size") or 0),
                is_selected=bool(f.get("is_selected", False)),
                created_at=_str_to_dt(f.get("created_at") or ""),
                user_id=f.get("user_id"),
                source=str(f.get("source") or "upload"),
                role=str(f.get("role") or "source"),
                task_uuid=f.get("task_uuid"),
                origin_file_id=f.get("origin_file_id"),
                storage_key=f.get("storage_key"),
                mime_type=f.get("mime_type"),
                file_hash=f.get("file_hash"),
                deleted_at=_str_to_dt(f["deleted_at"]) if f.get("deleted_at") else None,
            )
            for f in flist
        ]

    return True


def save_memory_store(store: Any, config: Optional[SystemConfig] = None) -> None:
    path = _store_file(config)
    payload = serialize_memory_store(store)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

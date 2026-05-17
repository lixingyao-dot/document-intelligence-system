"""会话和消息的内存存储（数据库未启用时使用）"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import FileRow, MessageRow, SessionListItem, SessionRow, SessionWithMessages


class MemoryStore:
    """内存存储"""

    def __init__(self):
        self._sessions: Dict[int, SessionRow] = {}
        self._sessions_by_uuid: Dict[str, SessionRow] = {}
        self._messages: Dict[int, List[MessageRow]] = {}
        self._session_files: Dict[int, List[FileRow]] = {}
        self._next_id = 1

    def _gen_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid


# 全局内存存储实例
_store = MemoryStore()
_loaded_work_dirs: set[str] = set()


def _ensure_json_loaded(config=None) -> None:
    """从 work_dir/sessions/chat_store.json 恢复（每个 work_dir 仅加载一次）。"""
    from config import get_config

    cfg = config or get_config()
    key = str(Path(cfg.work_dir).resolve())
    if key in _loaded_work_dirs:
        return
    _loaded_work_dirs.add(key)
    from db.session_json_persistence import load_into_memory_store

    load_into_memory_store(_store, cfg)


def _persist_json(config=None) -> None:
    from config import get_config
    from db.session_json_persistence import save_memory_store

    save_memory_store(_store, config or get_config())


def _utc_iso(dt) -> str:
    from utils.datetime_util import utc_iso

    return utc_iso(dt)


def _now_iso() -> str:
    return _utc_iso(datetime.utcnow())


def _gen_session_id() -> str:
    return str(uuid.uuid4())


# ============ 会话操作 ============

def create_session(
    title: str = "新会话",
    current_mode: str = "default_conversation",
    config=None,
    user_id: Optional[str] = None,
) -> SessionRow:
    """创建新会话"""
    _ensure_json_loaded(config)
    sid = _store._gen_id()
    session_id = _gen_session_id()
    now = datetime.utcnow()

    session = SessionRow(
        id=sid,
        session_id=session_id,
        title=title,
        current_mode=current_mode,
        created_at=now,
        updated_at=now,
        user_id=user_id,
    )
    _store._sessions[sid] = session
    _store._sessions_by_uuid[session_id] = session
    _store._messages[sid] = []
    _store._session_files[sid] = []
    _persist_json(config)
    return session


def get_session_by_id(
    session_id: str,
    config=None,
) -> Optional[SessionRow]:
    """根据 session_id 获取会话"""
    _ensure_json_loaded(config)
    return _store._sessions_by_uuid.get(session_id)


def list_sessions(
    limit: int = 50,
    offset: int = 0,
    config=None,
) -> tuple:
    """获取会话列表"""
    _ensure_json_loaded(config)
    sessions = sorted(
        _store._sessions.values(),
        key=lambda s: s.updated_at,
        reverse=True,
    )
    total = len(sessions)
    items = [
        SessionListItem(
            session_id=s.session_id,
            title=s.title,
            current_mode=s.current_mode,
            message_count=len(_store._messages.get(s.id, [])),
            created_at=_utc_iso(s.created_at),
            updated_at=_utc_iso(s.updated_at),
        )
        for s in sessions[offset:offset + limit]
    ]
    return items, total


def update_session(
    session_id: str,
    title: Optional[str] = None,
    current_mode: Optional[str] = None,
    config=None,
) -> Optional[SessionRow]:
    """更新会话"""
    _ensure_json_loaded(config)
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return None

    if title is not None:
        session.title = title
    if current_mode is not None:
        session.current_mode = current_mode
    session.updated_at = datetime.utcnow()
    _persist_json(config)
    return session


def delete_session(
    session_id: str,
    config=None,
) -> bool:
    """删除会话"""
    _ensure_json_loaded(config)
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return False

    sid = session.id
    del _store._sessions_by_uuid[session_id]
    del _store._sessions[sid]
    _store._messages.pop(sid, None)
    _store._session_files.pop(sid, None)
    _persist_json(config)
    return True


# ============ 消息操作 ============

def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
    config=None,
    user_id: Optional[str] = None,
) -> MessageRow:
    """添加消息"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    now = datetime.utcnow()
    msg = MessageRow(
        id=_store._gen_id(),
        session_id=session.id,
        role=role,
        content=content,
        metadata=metadata,
        created_at=now,
        user_id=user_id or session.user_id,
    )
    _store._messages[session.id].append(msg)

    # 更新会话时间
    session.updated_at = now
    _persist_json(config)
    return msg


def get_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    config=None,
) -> List[MessageRow]:
    """获取会话消息"""
    _ensure_json_loaded(config)
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return []
    msgs = _store._messages.get(session.id, [])
    return msgs[offset:offset + limit]


def get_session_with_messages(
    session_id: str,
    config=None,
) -> Optional[SessionWithMessages]:
    """获取会话及其所有消息"""
    session = get_session_by_id(session_id, config)
    if not session:
        return None
    messages = get_messages(session_id, config=config)
    return SessionWithMessages(session=session, messages=messages)


# ============ 文件操作 ============

def add_session_file(
    session_id: str,
    file_name: str,
    file_type: str,
    file_path: str,
    file_size: int,
    config=None,
    user_id: Optional[str] = None,
    source: str = "upload",
    role: str = "source",
    task_uuid: Optional[str] = None,
    origin_file_id: Optional[int] = None,
    storage_key: Optional[str] = None,
    mime_type: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> FileRow:
    """添加会话文件"""
    _ensure_json_loaded(config)
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    now = datetime.utcnow()
    frow = FileRow(
        id=_store._gen_id(),
        session_id=session.id,
        file_name=file_name,
        file_type=file_type,
        file_path=file_path,
        file_size=file_size,
        is_selected=False,
        created_at=now,
        user_id=user_id or session.user_id,
        source=source,
        role=role,
        task_uuid=task_uuid,
        origin_file_id=origin_file_id,
        storage_key=storage_key,
        mime_type=mime_type,
        file_hash=file_hash,
    )
    _store._session_files[session.id].append(frow)
    _persist_json(config)
    return frow


def get_session_files(
    session_id: str,
    file_type: Optional[str] = None,
    config=None,
) -> List[FileRow]:
    """获取会话文件列表"""
    _ensure_json_loaded(config)
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return []
    files = _store._session_files.get(session.id, [])
    if file_type:
        return [f for f in files if f.file_type == file_type]
    return files


def update_file_selection(
    file_id: int,
    is_selected: bool,
    config=None,
) -> bool:
    """更新文件勾选状态"""
    _ensure_json_loaded(config)
    for files in _store._session_files.values():
        for f in files:
            if f.id == file_id:
                f.is_selected = is_selected
                _persist_json(config)
                return True
    return False


def delete_session_file(
    file_id: int,
    config=None,
) -> bool:
    """删除会话文件"""
    _ensure_json_loaded(config)
    for files in _store._session_files.values():
        for i, f in enumerate(files):
            if f.id == file_id:
                files.pop(i)
                _persist_json(config)
                return True
    return False


# ---------------------------------------------------------------------------
# 文档库（内存存储，数据库未启用时使用）
# ---------------------------------------------------------------------------

_library_store_spaces: List[dict] = []
_library_store_docs: List[dict] = []
_library_store_next_space_id = 1
_library_store_next_doc_id = 1


def memory_create_library_space(
    name: str,
    icon: str = "📁",
    description: Optional[str] = None,
    config=None,
    user_id: Optional[str] = None,
):
    global _library_store_next_space_id
    from db.library_repository import LibrarySpaceRow
    sid = str(uuid.uuid4())
    now = datetime.utcnow()
    _library_store_spaces.append({
        "id": sid,
        "user_id": user_id,
        "name": name,
        "icon": icon,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "_num": _library_store_next_space_id,
    })
    _library_store_next_space_id += 1
    doc_count = sum(1 for d in _library_store_docs if d["space_id"] == sid and d.get("deleted_at") is None)
    return LibrarySpaceRow(
        id=sid, user_id=user_id, name=name, icon=icon,
        description=description, created_at=now, updated_at=now, doc_count=doc_count,
    )


def memory_get_library_spaces(config=None, user_id: Optional[str] = None):
    from db.library_repository import LibrarySpaceRow
    result = []
    for s in _library_store_spaces:
        if user_id and s.get("user_id") and s["user_id"] != user_id:
            continue
        doc_count = sum(1 for d in _library_store_docs if d["space_id"] == s["id"] and d.get("deleted_at") is None)
        result.append(LibrarySpaceRow(
            id=str(s["id"]), user_id=s.get("user_id"), name=s["name"], icon=s.get("icon", "📁"),
            description=s.get("description"), created_at=s["created_at"], updated_at=s["updated_at"],
            doc_count=doc_count,
        ))
    return result


def memory_get_library_space_by_id(space_id: str, config=None):
    from db.library_repository import LibrarySpaceRow
    for s in _library_store_spaces:
        if str(s["id"]) == space_id:
            doc_count = sum(1 for d in _library_store_docs if d["space_id"] == s["id"] and d.get("deleted_at") is None)
            return LibrarySpaceRow(
                id=str(s["id"]), user_id=s.get("user_id"), name=s["name"], icon=s.get("icon", "📁"),
                description=s.get("description"), created_at=s["created_at"], updated_at=s["updated_at"],
                doc_count=doc_count,
            )
    return None


def memory_update_library_space(space_id, name=None, icon=None, description=None, config=None, user_id=None):
    from db.library_repository import LibrarySpaceRow
    for s in _library_store_spaces:
        if str(s["id"]) == space_id:
            if name is not None:
                s["name"] = name
            if icon is not None:
                s["icon"] = icon
            if description is not None:
                s["description"] = description
            s["updated_at"] = datetime.utcnow()
            doc_count = sum(1 for d in _library_store_docs if d["space_id"] == s["id"] and d.get("deleted_at") is None)
            return LibrarySpaceRow(
                id=str(s["id"]), user_id=s.get("user_id"), name=s["name"], icon=s.get("icon", "📁"),
                description=s.get("description"), created_at=s["created_at"], updated_at=s["updated_at"],
                doc_count=doc_count,
            )
    return None


def memory_delete_library_space(space_id, config=None):
    global _library_store_spaces
    _library_store_spaces = [s for s in _library_store_spaces if str(s["id"]) != space_id]
    _library_store_docs[:] = [d for d in _library_store_docs if str(d["space_id"]) != space_id]
    return True


def memory_add_library_doc(
    space_id, file_name, file_size, config=None, user_id=None,
    mime_type=None, storage_key=None, blob_url=None,
):
    from db.library_repository import LibraryDocRow
    global _library_store_next_doc_id
    did = str(uuid.uuid4())
    now = datetime.utcnow()
    _library_store_docs.append({
        "id": did,
        "space_id": space_id,
        "user_id": user_id,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
        "file_extension": file_name.rsplit(".", 1)[-1].lower() if "." in file_name else None,
        "storage_key": storage_key,
        "blob_url": blob_url,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "_num": _library_store_next_doc_id,
    })
    _library_store_next_doc_id += 1
    return LibraryDocRow(
        id=did, space_id=space_id, user_id=user_id, file_name=file_name,
        file_size=file_size, mime_type=mime_type,
        file_extension=file_name.rsplit(".", 1)[-1].lower() if "." in file_name else None,
        storage_key=storage_key, blob_url=blob_url,
        created_at=now, updated_at=now, deleted_at=None,
    )


def memory_get_library_docs(space_id, config=None, user_id=None):
    from db.library_repository import LibraryDocRow
    result = []
    for d in _library_store_docs:
        if str(d["space_id"]) != space_id or d.get("deleted_at") is not None:
            continue
        if user_id and d.get("user_id") and d["user_id"] != user_id:
            continue
        result.append(LibraryDocRow(
            id=str(d["id"]), space_id=str(d["space_id"]), user_id=d.get("user_id"),
            file_name=d["file_name"], file_size=d.get("file_size", 0),
            mime_type=d.get("mime_type"), file_extension=d.get("file_extension"),
            storage_key=d.get("storage_key"), blob_url=d.get("blob_url"),
            created_at=d["created_at"], updated_at=d["updated_at"], deleted_at=d.get("deleted_at"),
        ))
    return result


def memory_get_library_doc_by_id(doc_id, config=None, user_id=None):
    from db.library_repository import LibraryDocRow
    for d in _library_store_docs:
        if str(d["id"]) == doc_id and d.get("deleted_at") is None:
            return LibraryDocRow(
                id=str(d["id"]), space_id=str(d["space_id"]), user_id=d.get("user_id"),
                file_name=d["file_name"], file_size=d.get("file_size", 0),
                mime_type=d.get("mime_type"), file_extension=d.get("file_extension"),
                storage_key=d.get("storage_key"), blob_url=d.get("blob_url"),
                created_at=d["created_at"], updated_at=d["updated_at"], deleted_at=d.get("deleted_at"),
            )
    return None


def memory_update_library_doc(doc_id, config=None, user_id=None):
    from db.library_repository import LibraryDocRow
    for d in _library_store_docs:
        if str(d["id"]) == doc_id and d.get("deleted_at") is None:
            d["updated_at"] = datetime.utcnow()
            return LibraryDocRow(
                id=str(d["id"]), space_id=str(d["space_id"]), user_id=d.get("user_id"),
                file_name=d["file_name"], file_size=d.get("file_size", 0),
                mime_type=d.get("mime_type"), file_extension=d.get("file_extension"),
                storage_key=d.get("storage_key"), blob_url=d.get("blob_url"),
                created_at=d["created_at"], updated_at=d["updated_at"], deleted_at=d.get("deleted_at"),
            )
    return None


def memory_delete_library_doc(doc_id, config=None, user_id=None):
    for d in _library_store_docs:
        if str(d["id"]) == doc_id and d.get("deleted_at") is None:
            d["deleted_at"] = datetime.utcnow()
            return True
    return False

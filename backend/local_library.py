"""
文档库本地 JSON + 文件系统实现（无 PostgreSQL）
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.bootstrap import get_data_dir

_META_FILE = "library_meta.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    iso = dt.isoformat()
    return iso if iso.endswith("Z") else iso.replace("+00:00", "Z")


def _meta_path() -> Path:
    return get_data_dir() / "workspace" / "library" / _META_FILE


def _load_meta() -> Dict[str, Any]:
    path = _meta_path()
    if not path.exists():
        return {"spaces": {}, "docs": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("spaces", {})
            data.setdefault("docs", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"spaces": {}, "docs": {}}


def _save_meta(data: Dict[str, Any]) -> None:
    path = _meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _space_dir(space_id: str) -> Path:
    return get_data_dir() / "workspace" / "library" / space_id


def list_spaces() -> List[Dict[str, Any]]:
    meta = _load_meta()
    out = []
    for sid, s in meta["spaces"].items():
        doc_count = sum(1 for d in meta["docs"].values() if d.get("space_id") == sid and not d.get("deleted"))
        out.append({
            "id": sid,
            "name": s.get("name", "未命名"),
            "icon": s.get("icon", "BookOpen"),
            "description": s.get("description"),
            "doc_count": doc_count,
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
        })
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def create_space(name: str, icon: str = "BookOpen", description: Optional[str] = None) -> Dict[str, Any]:
    meta = _load_meta()
    sid = str(uuid.uuid4())
    now = _utc_now()
    meta["spaces"][sid] = {
        "name": name,
        "icon": icon,
        "description": description or "",
        "created_at": _fmt(now),
        "updated_at": _fmt(now),
    }
    _save_meta(meta)
    _space_dir(sid).mkdir(parents=True, exist_ok=True)
    return {
        "id": sid,
        "name": name,
        "icon": icon,
        "description": description or "",
        "doc_count": 0,
        "created_at": _fmt(now),
        "updated_at": _fmt(now),
    }


def get_doc_record(doc_id: str) -> Optional[tuple[str, Dict[str, Any]]]:
    meta = _load_meta()
    d = meta["docs"].get(doc_id)
    if not d or d.get("deleted"):
        return None
    return str(d.get("space_id", "")), d


def get_space(space_id: str) -> Optional[Dict[str, Any]]:
    for s in list_spaces():
        if s["id"] == space_id:
            return s
    return None


def delete_space(space_id: str) -> bool:
    meta = _load_meta()
    if space_id not in meta["spaces"]:
        return False
    del meta["spaces"][space_id]
    meta["docs"] = {k: v for k, v in meta["docs"].items() if v.get("space_id") != space_id}
    _save_meta(meta)
    d = _space_dir(space_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return True


def list_docs(space_id: str) -> List[Dict[str, Any]]:
    meta = _load_meta()
    out = []
    for did, d in meta["docs"].items():
        if d.get("space_id") != space_id or d.get("deleted"):
            continue
        out.append(_doc_public(did, d))
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def _doc_public(doc_id: str, d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc_id,
        "space_id": d.get("space_id", ""),
        "name": d.get("file_name", ""),
        "file_name": d.get("file_name", ""),
        "size": d.get("file_size", 0),
        "file_size": d.get("file_size", 0),
        "mime_type": d.get("mime_type"),
        "file_extension": d.get("file_extension"),
        "storage_key": d.get("storage_key"),
        "blob_url": None,
        "created_at": d.get("created_at", ""),
        "updated_at": d.get("updated_at", ""),
    }


def add_doc(space_id: str, file_name: str, file_bytes: bytes, mime_type: Optional[str] = None) -> Dict[str, Any]:
    meta = _load_meta()
    if space_id not in meta["spaces"]:
        raise ValueError("空间不存在")
    did = str(uuid.uuid4())
    ext = Path(file_name).suffix.lstrip(".").lower()
    dest = _space_dir(space_id) / f"{did}_{file_name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)
    now = _utc_now()
    record = {
        "space_id": space_id,
        "file_name": file_name,
        "file_size": len(file_bytes),
        "mime_type": mime_type,
        "file_extension": ext,
        "storage_key": str(dest.relative_to(get_data_dir())),
        "local_path": str(dest),
        "created_at": _fmt(now),
        "updated_at": _fmt(now),
        "deleted": False,
    }
    meta["docs"][did] = record
    meta["spaces"][space_id]["updated_at"] = _fmt(now)
    _save_meta(meta)
    return _doc_public(did, record)


def get_doc(space_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
    meta = _load_meta()
    d = meta["docs"].get(doc_id)
    if not d or d.get("space_id") != space_id or d.get("deleted"):
        return None
    return _doc_public(doc_id, d)


def delete_doc(space_id: str, doc_id: str) -> bool:
    meta = _load_meta()
    d = meta["docs"].get(doc_id)
    if not d or d.get("space_id") != space_id:
        return False
    d["deleted"] = True
    lp = d.get("local_path")
    if lp and Path(lp).exists():
        try:
            Path(lp).unlink()
        except OSError:
            pass
    _save_meta(meta)
    return True


def resolve_doc_path(space_id: str, doc_id: str) -> Optional[Path]:
    meta = _load_meta()
    d = meta["docs"].get(doc_id)
    if not d or d.get("space_id") != space_id or d.get("deleted"):
        return None
    lp = d.get("local_path")
    if lp and Path(lp).exists():
        return Path(lp)
    sk = d.get("storage_key")
    if sk:
        p = get_data_dir() / sk
        if p.exists():
            return p
    return None

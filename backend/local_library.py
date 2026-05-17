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


def _safe_basename(file_name: str) -> str:
    """防止路径穿越，仅保留文件名部分。"""
    name = Path(file_name or "unnamed").name
    if not name or name in (".", ".."):
        return "unnamed"
    return name


def _doc_dir(space_id: str, doc_id: str) -> Path:
    return _space_dir(space_id) / doc_id


def _doc_file_path(space_id: str, doc_id: str, file_name: str) -> Path:
    """新布局：{space_id}/{doc_id}/{原始文件名}"""
    return _doc_dir(space_id, doc_id) / _safe_basename(file_name)


def _legacy_doc_path(space_id: str, doc_id: str, file_name: str) -> Path:
    return _space_dir(space_id) / f"{doc_id}_{_safe_basename(file_name)}"


def _apply_record_paths(record: Dict[str, Any], dest: Path) -> None:
    record["storage_key"] = str(dest.relative_to(get_data_dir()))
    record["local_path"] = str(dest)


def _find_legacy_path(space_id: str, doc_id: str, file_name: str) -> Optional[Path]:
    legacy = _legacy_doc_path(space_id, doc_id, file_name)
    if legacy.is_file():
        return legacy
    pattern = f"{doc_id}_*"
    matches = sorted(_space_dir(space_id).glob(pattern))
    for p in matches:
        if p.is_file():
            return p
    return None


def _migrate_doc_to_dir_layout(
    meta: Dict[str, Any], space_id: str, doc_id: str, record: Dict[str, Any]
) -> Optional[Path]:
    """将旧版 {doc_id}_{文件名} 迁移到 {doc_id}/{文件名}。"""
    file_name = record.get("file_name") or "unnamed"
    new_path = _doc_file_path(space_id, doc_id, file_name)
    if new_path.is_file():
        _apply_record_paths(record, new_path)
        return new_path

    legacy = _find_legacy_path(space_id, doc_id, file_name)
    if not legacy or not legacy.is_file():
        lp = record.get("local_path")
        if lp:
            p = Path(lp)
            if p.is_file():
                if p.parent.name == doc_id:
                    _apply_record_paths(record, p)
                    return p
                new_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(p), str(new_path))
                    _apply_record_paths(record, new_path)
                    meta["docs"][doc_id] = record
                    _save_meta(meta)
                    return new_path
                except OSError:
                    return p
        return None

    new_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy), str(new_path))
    except OSError:
        try:
            shutil.copy2(legacy, new_path)
            legacy.unlink(missing_ok=True)
        except OSError:
            return legacy
    _apply_record_paths(record, new_path)
    meta["docs"][doc_id] = record
    _save_meta(meta)
    return new_path


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
    safe_name = _safe_basename(file_name)
    ext = Path(safe_name).suffix.lstrip(".").lower()
    dest = _doc_file_path(space_id, did, safe_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)
    now = _utc_now()
    record = {
        "space_id": space_id,
        "file_name": safe_name,
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
    doc_dir = _doc_dir(space_id, doc_id)
    if doc_dir.is_dir():
        shutil.rmtree(doc_dir, ignore_errors=True)
    else:
        lp = d.get("local_path")
        if lp and Path(lp).exists():
            try:
                Path(lp).unlink()
            except OSError:
                pass
        legacy = _find_legacy_path(space_id, doc_id, d.get("file_name") or "")
        if legacy and legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
    _save_meta(meta)
    return True


def resolve_doc_path(space_id: str, doc_id: str) -> Optional[Path]:
    meta = _load_meta()
    d = meta["docs"].get(doc_id)
    if not d or d.get("space_id") != space_id or d.get("deleted"):
        return None

    migrated = _migrate_doc_to_dir_layout(meta, space_id, doc_id, d)
    if migrated and migrated.is_file():
        return migrated

    lp = d.get("local_path")
    if lp:
        p = Path(lp)
        if p.is_file():
            return p
    sk = d.get("storage_key")
    if sk:
        p = get_data_dir() / sk
        if p.is_file():
            return p
    return None

"""桌面版文档库 API（路径与响应格式与线上一致，本地 JSON + 文件）"""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend import local_library as lib

router = APIRouter(prefix="/api/library", tags=["文档库管理"])


class SpaceListResponse(BaseModel):
    spaces: List[Dict[str, Any]]


class DocListResponse(BaseModel):
    docs: List[Dict[str, Any]]
    total: int


class CreateSpaceBody(BaseModel):
    name: str
    icon: str = "BookOpen"
    description: Optional[str] = None


class ExportBatchRequest(BaseModel):
    doc_ids: List[str] = Field(default_factory=list, min_length=1)
    archive_name: Optional[str] = None


def _unique_archive_entry_name(file_name: str, used: Dict[str, int]) -> str:
    safe = Path(file_name or "unnamed").name
    if safe not in used:
        used[safe] = 0
        return safe
    used[safe] += 1
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    return f"{stem}_{used[safe]}{suffix}"


def _build_docs_zip(entries: List[Tuple[str, Path]], *, skipped: List[str]) -> BytesIO:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names: Dict[str, int] = {}
        for file_name, path in entries:
            arcname = _unique_archive_entry_name(file_name, used_names)
            zf.write(path, arcname=arcname)
        if skipped:
            manifest = "以下文档未能导出（文件缺失）：\n" + "\n".join(skipped)
            zf.writestr("_export_skipped.txt", manifest.encode("utf-8"))
    buffer.seek(0)
    return buffer


def _zip_content_disposition(filename: str) -> str:
    ascii_name = "".join(c if c.isascii() and c not in '"\\' else "_" for c in filename) or "export.zip"
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


@router.get("/spaces", response_model=SpaceListResponse)
async def list_spaces():
    return SpaceListResponse(spaces=lib.list_spaces())


@router.post("/spaces")
async def create_space(body: CreateSpaceBody):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="空间名称不能为空")
    return lib.create_space(name, body.icon or "BookOpen", body.description)


@router.delete("/spaces/{space_id}")
async def delete_space(space_id: str):
    if not lib.delete_space(space_id):
        raise HTTPException(status_code=404, detail="空间不存在")
    return {"success": True}


@router.get("/spaces/{space_id}/docs", response_model=DocListResponse)
async def list_docs(space_id: str):
    if not lib.get_space(space_id):
        raise HTTPException(status_code=404, detail="空间不存在")
    docs = lib.list_docs(space_id)
    return DocListResponse(docs=docs, total=len(docs))


@router.post("/spaces/{space_id}/docs")
async def upload_doc(space_id: str, file: UploadFile):
    if not lib.get_space(space_id):
        raise HTTPException(status_code=404, detail="空间不存在")
    content = await file.read()
    return lib.add_doc(space_id, file.filename or "file", content, file.content_type)


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: str):
    pair = lib.get_doc_record(doc_id)
    if not pair:
        raise HTTPException(status_code=404, detail="文档不存在")
    space_id, _ = pair
    lib.delete_doc(space_id, doc_id)
    return {"success": True}


@router.post("/docs/delete-batch")
async def delete_docs_batch(body: Dict[str, Any]):
    doc_ids: List[str] = body.get("doc_ids") or []
    results = []
    for doc_id in doc_ids:
        pair = lib.get_doc_record(doc_id)
        if not pair:
            results.append({"doc_id": doc_id, "success": False})
            continue
        space_id, _ = pair
        results.append({"doc_id": doc_id, "success": lib.delete_doc(space_id, doc_id)})
    return {"results": results}


@router.get("/docs/{doc_id}/download")
async def download_doc(doc_id: str):
    pair = lib.get_doc_record(doc_id)
    if not pair:
        raise HTTPException(status_code=404, detail="文档不存在")
    space_id, rec = pair
    path = lib.resolve_doc_path(space_id, doc_id)
    if not path:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=rec.get("file_name") or path.name)


@router.post("/docs/export-batch")
async def export_docs_batch(body: ExportBatchRequest):
    """批量导出文档为 ZIP。"""
    doc_ids = [str(d).strip() for d in body.doc_ids if str(d).strip()]
    if not doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids 不能为空")

    entries: List[Tuple[str, Path]] = []
    skipped: List[str] = []

    for doc_id in doc_ids:
        pair = lib.get_doc_record(doc_id)
        if not pair:
            skipped.append(f"{doc_id}（文档不存在）")
            continue
        space_id, rec = pair
        path = lib.resolve_doc_path(space_id, doc_id)
        if not path or not path.is_file():
            skipped.append(f"{rec.get('file_name') or doc_id}（文件不存在）")
            continue
        entries.append((rec.get("file_name") or path.name, path))

    if not entries:
        raise HTTPException(status_code=404, detail="没有可导出的文件")

    zip_buffer = _build_docs_zip(entries, skipped=skipped)
    label = (body.archive_name or "documents").strip() or "documents"
    if not label.lower().endswith(".zip"):
        label = f"{label}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _zip_content_disposition(Path(label).name)},
    )

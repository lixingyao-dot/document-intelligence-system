"""
桌面版 FastAPI：复用主项目 API，挂载本地文档库与设置、静态前端。
"""
from __future__ import annotations

from backend.paths import ensure_sys_path, get_bundle_root, get_desktop_root

ensure_sys_path()

from backend.bootstrap import init_desktop_runtime  # noqa: E402

init_desktop_runtime()

from api.main import app  # noqa: E402
from backend.routers import library_local, settings  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

app.include_router(library_local.router)
app.include_router(settings.router)

FRONTEND_DIST = get_bundle_root() / "frontend" / "dist"
if not FRONTEND_DIST.is_dir():
    FRONTEND_DIST = get_desktop_root() / "frontend" / "dist"

_NO_STORE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="desktop-assets")

    @app.get("/")
    async def desktop_index():
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers=_NO_STORE_HEADERS,
        )

    @app.get("/{full_path:path}")
    async def desktop_spa(full_path: str):
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers=_NO_STORE_HEADERS,
        )

"""
最小 HTTP API

启动（任选其一）:

1) 推荐：进入 src 再启动
   cd src
   python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

2) 在仓库根目录：先设置 PYTHONPATH 再启动（PowerShell）
   $env:PYTHONPATH = "src"
   python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_SRC = Path(__file__).resolve().parent.parent
_ROOT = _SRC.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
load_dotenv(_ROOT / ".env")

from config import load_config, set_config  # noqa: E402
from db.connection import health_check, is_database_configured  # noqa: E402


def _reset_config():
    import config as cfgmod

    cfgmod._config = None
    set_config(load_config())


_reset_config()


def err_body(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def ok_body(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    _reset_config()
    cfg = load_config()
    level_name = str(getattr(cfg, "log_level", None) or os.getenv("LOG_LEVEL", "INFO")).upper()
    lvl = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    for name in (
        "service.agent_service",
        "api.messages.ws_llm",
        "api.messages.ws_conn",
    ):
        logging.getLogger(name).setLevel(lvl)
    logging.getLogger("api.main").info("startup log_level=%s", level_name)
    yield


app = FastAPI(title="Document Intelligence API", version="0.1.0", lifespan=_app_lifespan)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=err_body(
            "VALIDATION_ERROR",
            "请求参数校验失败",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    from fastapi.exceptions import RequestValidationError, ResponseValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    if isinstance(exc, RequestValidationError):
        return await validation_handler(request, exc)
    if isinstance(exc, ResponseValidationError):
        return JSONResponse(
            status_code=500,
            content=err_body(
                "RESPONSE_VALIDATION_ERROR",
                "响应数据与接口契约不一致，请检查消息字段类型",
                {"errors": exc.errors()},
            ),
        )
    if isinstance(exc, StarletteHTTPException):
        detail = exc.detail
        body: Any = {"detail": detail} if isinstance(detail, str) else {"detail": detail}
        return JSONResponse(status_code=exc.status_code, content=body)
    import traceback

    traceback.print_exc()
    return JSONResponse(status_code=500, content=err_body("INTERNAL_ERROR", str(exc)))


@app.get("/health")
async def health():
    """服务与数据库连通性（桌面版 database_enabled 恒为 false）。"""
    _reset_config()
    cfg = load_config()
    db_ok = False
    if cfg.database.enabled and is_database_configured(cfg):
        ok, _ = health_check(cfg)
        db_ok = ok
    return ok_body(
        {
            "status": "ok",
            "database_enabled": cfg.database.enabled,
            "database_ok": db_ok,
        }
    )


from api.routers import sessions, messages, files, agents, workflows  # noqa: E402
from api.routers.files import download_router, temp_router  # noqa: E402

app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(files.router)
app.include_router(temp_router)
app.include_router(download_router)
app.include_router(agents.router)
app.include_router(workflows.router)

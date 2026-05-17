"""
最小 HTTP API（契约：integration-contract-v1.md 错误体）

启动（任选其一）:

1) 推荐：进入 src 再启动（避免 ModuleNotFoundError: No module named 'api'）
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 项目根 .env、src 在路径中
_SRC = Path(__file__).resolve().parent.parent
_ROOT = _SRC.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
load_dotenv(_ROOT / ".env")

from config import load_config, set_config  # noqa: E402
from db.connection import health_check, is_database_configured  # noqa: E402
from db.repository import (  # noqa: E402
    ExtractionResultRow,
    TaskRow,
    get_latest_extraction_by_task_id,
    get_task_by_task_id,
    get_task_timeline,
    insert_agent_log,
    insert_document_asset,
    insert_fill_report,
    set_task_review,
)


def _reset_config():
    import config as cfgmod

    cfgmod._config = None
    set_config(load_config())


_reset_config()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def task_to_dict(t: TaskRow) -> Dict[str, Any]:
    return {
        "id": t.id,
        "task_id": t.task_id,
        "task_type": t.task_type,
        "status": t.status,
        "error_code": t.error_code,
        "error_message": t.error_message,
        "parent_task_id": t.parent_task_id,
        "metadata": t.metadata,
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
        "started_at": _iso(t.started_at),
        "completed_at": _iso(t.completed_at),
    }


def extraction_to_dict(e: ExtractionResultRow) -> Dict[str, Any]:
    return {
        "id": e.id,
        "task_uuid": e.task_uuid,
        "schema_version": e.schema_version,
        "payload": e.payload,
        "result_version": e.result_version,
        "created_at": _iso(e.created_at),
    }


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
    """启动时配置 logging，使业务 logger 与 print 一样出现在 Uvicorn 终端。"""
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
    """
    未捕获异常：返回 JSON 便于 axios 读取 error.message。
    须识别 Starlette 的 HTTPException（部分路径抛出基类），否则会被误判为 500。
    """
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
    """服务与数据库连通性。"""
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


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """按业务 task_id 查询任务。"""
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    t = get_task_by_task_id(task_id, cfg)
    if not t:
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    return ok_body(task_to_dict(t))


@app.get("/tasks/{task_id}/extraction")
async def get_extraction(task_id: str):
    """按业务 task_id 取最新一条抽取结果。"""
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    if not get_task_by_task_id(task_id, cfg):
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    ex = get_latest_extraction_by_task_id(task_id, cfg)
    if not ex:
        return JSONResponse(
            status_code=404,
            content=err_body("NOT_FOUND", "该任务暂无抽取结果"),
        )
    return ok_body(extraction_to_dict(ex))


@app.get("/tasks/{task_id}/timeline")
async def get_timeline(task_id: str):
    """任务步骤 + 审计聚合，便于链路演示。"""
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    tl = get_task_timeline(task_id, cfg)
    if not tl:
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    return ok_body(tl)


@app.post("/tasks/{task_id}/document-assets")
async def post_document_asset(task_id: str, body: Dict[str, Any]):
    """登记文档元数据（本地路径或 storage_key 等），大文件本体仍走存储。"""
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    t = get_task_by_task_id(task_id, cfg)
    if not t:
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    try:
        aid = insert_document_asset(t.id, body, cfg)
    except Exception as e:
        return JSONResponse(status_code=400, content=err_body("VALIDATION_ERROR", str(e)))
    return ok_body({"document_asset_id": aid})


@app.post("/tasks/{task_id}/review")
async def post_review(task_id: str, body: Dict[str, Any]):
    """
    人工复核：body.action = mark_review | approve | reject，可选 comment。
    """
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    action = body.get("action")
    if not action:
        return JSONResponse(status_code=400, content=err_body("VALIDATION_ERROR", "缺少 action"))
    comment = body.get("comment")
    try:
        set_task_review(task_id, str(action), comment=comment, config=cfg)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_body("VALIDATION_ERROR", str(e)))
    t = get_task_by_task_id(task_id, cfg)
    return ok_body({"task": task_to_dict(t) if t else None})


@app.post("/tasks/{task_id}/fill-report")
async def post_fill_report(task_id: str, body: Dict[str, Any]):
    """
    提交填表报告 JSON（须含 schema_version、output_file）。
    """
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    t = get_task_by_task_id(task_id, cfg)
    if not t:
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    try:
        rid = insert_fill_report(t.id, body, cfg)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_body("VALIDATION_ERROR", str(e)))
    except Exception as e:
        return JSONResponse(status_code=500, content=err_body("INTERNAL_ERROR", str(e)))
    return ok_body({"fill_report_id": rid})


@app.post("/tasks/{task_id}/agent-logs")
async def post_agent_log(task_id: str, body: Dict[str, Any]):
    """
    提交文档编辑/编排执行日志 JSON（须含 action、summary）。
    """
    _reset_config()
    cfg = load_config()
    if not cfg.database.enabled:
        return JSONResponse(status_code=503, content=err_body("DB_UNAVAILABLE", "数据库未启用"))
    t = get_task_by_task_id(task_id, cfg)
    if not t:
        return JSONResponse(status_code=404, content=err_body("NOT_FOUND", f"任务不存在: {task_id}"))
    try:
        rid = insert_agent_log(t.id, body, cfg)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_body("VALIDATION_ERROR", str(e)))
    except Exception as e:
        return JSONResponse(status_code=500, content=err_body("INTERNAL_ERROR", str(e)))
    return ok_body({"agent_log_id": rid})


# ============ 注册新路由 ============

from api.routers import auth, sessions, messages, files, agents, library, workflows  # noqa: E402
from api.routers.files import download_router, temp_router  # noqa: E402

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(files.router)
app.include_router(temp_router)
app.include_router(download_router)
app.include_router(agents.router)
app.include_router(library.router)
app.include_router(workflows.router)

"""会话管理 API 路由"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from config import load_config
from utils.datetime_util import utc_iso
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import (
    create_session,
    delete_session,
    get_session_by_id,
    list_sessions,
    update_session,
)

router = APIRouter(prefix="/api/sessions", tags=["会话管理"])


class CreateSessionRequest(BaseModel):
    title: str = Field(default="新会话", description="会话标题")
    current_mode: str = Field(default="default_conversation", description="当前模式")


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="会话标题")
    current_mode: Optional[str] = Field(default=None, description="当前模式")


class SessionResponse(BaseModel):
    session_id: str
    title: str
    current_mode: str
    user_id: Optional[str] = None
    created_at: str
    updated_at: str


class SessionListItemResponse(BaseModel):
    session_id: str
    title: str
    current_mode: str
    message_count: int
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    items: list[SessionListItemResponse]
    total: int


def _resolve_current_user(authorization: Optional[str], cfg):
    if not authorization:
        if cfg.auth.require_auth:
            raise HTTPException(status_code=401, detail="需要登录后访问")
        return None
    try:
        return resolve_user_from_authorization(authorization, cfg, required=True)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def _session_to_dict(s) -> Dict[str, Any]:
    user_id = getattr(s, "user_id", None)
    return {
        "session_id": s.session_id,
        "title": s.title,
        "current_mode": s.current_mode,
        "user_id": str(user_id) if user_id else None,
        "created_at": utc_iso(s.created_at),
        "updated_at": utc_iso(s.updated_at),
    }


@router.post("", response_model=SessionResponse)
async def create_session_api(request: CreateSessionRequest, authorization: Optional[str] = Header(default=None)):
    """创建新会话"""
    cfg = load_config()
    try:
        current_user = _resolve_current_user(authorization, cfg)
        session = create_session(
            title=request.title,
            current_mode=request.current_mode,
            config=cfg,
            user_id=current_user.id if current_user else None,
        )
        return _session_to_dict(session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=SessionListResponse)
async def list_sessions_api(limit: int = 50, offset: int = 0, authorization: Optional[str] = Header(default=None)):
    """获取会话列表"""
    cfg = load_config()
    try:
        current_user = _resolve_current_user(authorization, cfg)
        items, total = list_sessions(limit=limit, offset=offset, config=cfg, user_id=current_user.id if current_user else None)
        return SessionListResponse(
            items=[SessionListItemResponse(
                session_id=s.session_id,
                title=s.title,
                current_mode=s.current_mode,
                message_count=s.message_count,
                created_at=s.created_at or "",
                updated_at=s.updated_at or "",
            ) for s in items],
            total=total,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_api(session_id: str, authorization: Optional[str] = Header(default=None)):
    """获取单个会话详情"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _session_to_dict(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session_api(session_id: str, request: UpdateSessionRequest, authorization: Optional[str] = Header(default=None)):
    """更新会话（标题或模式）"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    session = update_session(
        session_id,
        title=request.title,
        current_mode=request.current_mode,
        config=cfg,
        user_id=current_user.id if current_user else None,
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _session_to_dict(session)


@router.delete("/{session_id}")
async def delete_session_api(session_id: str, authorization: Optional[str] = Header(default=None)):
    """删除会话"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    success = delete_session(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True}

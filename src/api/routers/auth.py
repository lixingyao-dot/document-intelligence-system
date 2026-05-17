"""认证 API 路由。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from config import load_config
from core.auth import create_access_token, hash_password, verify_password, bearer_token_from_header
from db.auth_repository import (
    authenticate_user,
    create_auth_session,
    create_user,
    get_user_by_id,
    get_user_by_phone,
    revoke_auth_session,
    resolve_user_from_authorization,
    update_user_last_login,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    phone: str = Field(..., description="手机号")
    password: str = Field(..., min_length=6, description="密码")
    display_name: Optional[str] = Field(default=None, description="昵称")


class LoginRequest(BaseModel):
    phone: str = Field(..., description="手机号")
    password: str = Field(..., description="密码")


class AuthUserResponse(BaseModel):
    id: str
    phone: str
    display_name: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    last_login_at: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: AuthUserResponse


def _user_to_dict(user) -> Dict[str, Any]:
    return {
        "id": user.id,
        "phone": user.phone,
        "display_name": user.display_name,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "updated_at": user.updated_at.isoformat() if user.updated_at else "",
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, http_request: Request):
    cfg = load_config()
    if not cfg.database.enabled:
        raise HTTPException(status_code=503, detail="数据库未启用")

    existing = get_user_by_phone(request.phone, cfg)
    if existing:
        raise HTTPException(status_code=409, detail="手机号已注册")

    password_hash = hash_password(request.password)
    user = create_user(request.phone, password_hash, request.display_name, cfg)
    access_token = create_access_token(
        secret_key=cfg.auth.secret_key,
        subject=user.id,
        phone=user.phone,
        display_name=user.display_name,
        status=user.status,
        expires_delta_minutes=cfg.auth.access_token_ttl_minutes,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=cfg.auth.access_token_ttl_minutes)
    create_auth_session(
        user.id,
        access_token,
        expires_at,
        user_agent=http_request.headers.get("user-agent"),
        ip_address=http_request.client.host if http_request.client else None,
        config=cfg,
    )
    update_user_last_login(user.id, cfg)
    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=cfg.auth.access_token_ttl_minutes * 60,
        user=AuthUserResponse(**_user_to_dict(user)),
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, http_request: Request):
    cfg = load_config()
    if not cfg.database.enabled:
        raise HTTPException(status_code=503, detail="数据库未启用")

    user = authenticate_user(request.phone, request.password, cfg)
    if not user:
        raise HTTPException(status_code=401, detail="手机号或密码错误")

    access_token = create_access_token(
        secret_key=cfg.auth.secret_key,
        subject=user.id,
        phone=user.phone,
        display_name=user.display_name,
        status=user.status,
        expires_delta_minutes=cfg.auth.access_token_ttl_minutes,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=cfg.auth.access_token_ttl_minutes)
    create_auth_session(
        user.id,
        access_token,
        expires_at,
        user_agent=http_request.headers.get("user-agent"),
        ip_address=http_request.client.host if http_request.client else None,
        config=cfg,
    )
    update_user_last_login(user.id, cfg)
    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=cfg.auth.access_token_ttl_minutes * 60,
        user=AuthUserResponse(**_user_to_dict(user)),
    )


@router.get("/me", response_model=AuthUserResponse)
async def me(authorization: Optional[str] = Header(default=None)):
    cfg = load_config()
    if not cfg.database.enabled:
        raise HTTPException(status_code=503, detail="数据库未启用")
    try:
        user = resolve_user_from_authorization(authorization, cfg, required=True)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return AuthUserResponse(**_user_to_dict(user))


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    cfg = load_config()
    if not cfg.database.enabled:
        raise HTTPException(status_code=503, detail="数据库未启用")
    token = bearer_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="缺少 Authorization Bearer token")
    revoked = revoke_auth_session(token, cfg)
    if not revoked:
        raise HTTPException(status_code=404, detail="登录会话不存在或已失效")
    return {"success": True}

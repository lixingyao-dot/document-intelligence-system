"""桌面版：本地 API Key / LLM 设置（按供应商写入 data/settings.json）"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.bootstrap import load_settings, save_settings
from backend.settings_store import merge_settings_update, public_settings_view
from config import load_config, set_config

router = APIRouter(prefix="/api/settings", tags=["桌面设置"])


class ProviderConfigPayload(BaseModel):
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class SettingsPayload(BaseModel):
    active_provider: Optional[str] = Field(default=None, description="deepseek | zhipu | openai")
    provider: Optional[str] = Field(default=None, description="要更新的供应商，默认当前选中")
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    providers: Optional[Dict[str, ProviderConfigPayload]] = None


@router.get("")
async def get_settings():
    return {"success": True, "data": public_settings_view(load_settings())}


@router.put("")
async def put_settings(body: SettingsPayload):
    current = load_settings()
    incoming = body.model_dump(exclude_unset=True)
    if body.providers:
        incoming["providers"] = {
            k: v.model_dump(exclude_unset=True) if hasattr(v, "model_dump") else v
            for k, v in body.providers.items()
        }
    merged = merge_settings_update(current, incoming)
    save_settings(merged)
    import config as cfgmod

    cfgmod._config = None
    set_config(load_config())
    return {"success": True, "data": public_settings_view(merged)}

"""桌面版 settings.json：按供应商分桶存储，并兼容旧版扁平格式。"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

PROVIDER_IDS = ("deepseek", "zhipu", "openai")

PROVIDER_MODELS: Dict[str, list] = {
    "deepseek": [
        {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash"},
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
        {"id": "deepseek-chat", "name": "DeepSeek Chat"},
        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner"},
    ],
    "zhipu": [
        {"id": "glm-4-flash", "name": "GLM-4 Flash"},
        {"id": "glm-4-air", "name": "GLM-4 Air"},
        {"id": "glm-4-plus", "name": "GLM-4 Plus"},
        {"id": "glm-4-long", "name": "GLM-4 Long"},
    ],
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
    ],
}

PROVIDER_META: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek",
        "default_model": "deepseek-v4-flash",
        "default_base_url": "https://api.deepseek.com",
        "api_key_field": "deepseek_api_key",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "default_model": "glm-4-flash",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_field": "zhipu_api_key",
    },
    "openai": {
        "label": "OpenAI 兼容",
        "default_model": "gpt-4o-mini",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_field": "openai_api_key",
    },
}

ENV_BY_PROVIDER = {
    "deepseek": {
        "api_key": "DEEPSEEK_API_KEY",
        "model": "DEEPSEEK_MODEL",
        "base_url": "DEEPSEEK_BASE_URL",
    },
    "zhipu": {
        "api_key": "ZHIPU_API_KEY",
        "model": "ZHIPU_MODEL",
        "base_url": "ZHIPU_BASE_URL",
    },
    "openai": {
        "api_key": "OPENAI_API_KEY",
        "model": "OPENAI_MODEL",
        "base_url": "OPENAI_BASE_URL",
    },
}


def _empty_provider_config() -> Dict[str, str]:
    return {"model": "", "base_url": "", "api_key": ""}


def _coerce_provider_entry(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return _empty_provider_config()
    return {
        "model": str(raw.get("model") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
    }


def normalize_settings(raw: Optional[dict]) -> Dict[str, Any]:
    """统一为 { active_provider, providers: { id: { model, base_url, api_key } } }。"""
    data = dict(raw or {})
    providers: Dict[str, Dict[str, str]] = {pid: _empty_provider_config() for pid in PROVIDER_IDS}

    if isinstance(data.get("providers"), dict):
        for pid in PROVIDER_IDS:
            providers[pid] = _coerce_provider_entry(data["providers"].get(pid))
        active = str(data.get("active_provider") or data.get("llm_provider") or "deepseek").strip().lower()
    else:
        active = str(data.get("llm_provider") or data.get("active_provider") or "deepseek").strip().lower()
        for pid in PROVIDER_IDS:
            field = PROVIDER_META[pid]["api_key_field"]
            providers[pid]["api_key"] = str(data.get(field) or "").strip()
        if active in providers:
            providers[active]["model"] = str(data.get("llm_model") or "").strip()
            providers[active]["base_url"] = str(data.get("llm_base_url") or "").strip()

    if active not in PROVIDER_IDS:
        active = "deepseek"

    return {"active_provider": active, "providers": providers}


def mask_api_key(key: Optional[str]) -> str:
    if not key or len(key) < 8:
        return ""
    return "*" * (len(key) - 4) + key[-4:]


def public_settings_view(data: dict) -> Dict[str, Any]:
    norm = normalize_settings(data)
    active = norm["active_provider"]
    providers_out: Dict[str, Any] = {}
    for pid in PROVIDER_IDS:
        cfg = norm["providers"][pid]
        providers_out[pid] = {
            "label": PROVIDER_META[pid]["label"],
            "model": cfg["model"],
            "base_url": cfg["base_url"],
            "default_model": PROVIDER_META[pid]["default_model"],
            "default_base_url": PROVIDER_META[pid]["default_base_url"],
            "models": PROVIDER_MODELS.get(pid, []),
            "api_key_masked": mask_api_key(cfg["api_key"]),
            "has_api_key": bool(cfg["api_key"]),
        }
    active_cfg = norm["providers"][active]
    return {
        "active_provider": active,
        "providers": providers_out,
        "model": active_cfg["model"],
        "base_url": active_cfg["base_url"],
        "api_key_masked": mask_api_key(active_cfg["api_key"]),
        "has_api_key": bool(active_cfg["api_key"]),
    }


def merge_settings_update(current: dict, payload: dict) -> dict:
    """合并保存：可切换 active_provider，并更新当前（或指定）供应商配置。"""
    norm = normalize_settings(current)
    if payload.get("active_provider"):
        pid = str(payload["active_provider"]).strip().lower()
        if pid in PROVIDER_IDS:
            norm["active_provider"] = pid

    target = str(payload.get("provider") or norm["active_provider"]).strip().lower()
    if target not in PROVIDER_IDS:
        target = norm["active_provider"]

    entry = norm["providers"][target]
    if "model" in payload and payload["model"] is not None:
        entry["model"] = str(payload["model"]).strip()
    if "base_url" in payload and payload["base_url"] is not None:
        entry["base_url"] = str(payload["base_url"]).strip()
    if payload.get("api_key") and str(payload["api_key"]).strip():
        entry["api_key"] = str(payload["api_key"]).strip()

    if isinstance(payload.get("providers"), dict):
        for pid, pcfg in payload["providers"].items():
            if pid not in PROVIDER_IDS or not isinstance(pcfg, dict):
                continue
            merged = _coerce_provider_entry(pcfg)
            cur = norm["providers"][pid]
            if merged["model"]:
                cur["model"] = merged["model"]
            if merged["base_url"]:
                cur["base_url"] = merged["base_url"]
            if merged["api_key"]:
                cur["api_key"] = merged["api_key"]

    norm["providers"][target] = entry
    return norm


def apply_settings_to_env(settings: dict) -> None:
    """写入进程环境，供 load_config() 使用。"""
    norm = normalize_settings(settings)
    active = norm["active_provider"]
    active_cfg = norm["providers"][active]

    os.environ["LLM_PROVIDER"] = active
    if active_cfg.get("model"):
        os.environ["LLM_MODEL"] = active_cfg["model"]
    elif "LLM_MODEL" in os.environ:
        os.environ.pop("LLM_MODEL", None)

    if active_cfg.get("base_url"):
        os.environ["LLM_BASE_URL"] = active_cfg["base_url"]
    elif "LLM_BASE_URL" in os.environ:
        os.environ.pop("LLM_BASE_URL", None)

    for pid in PROVIDER_IDS:
        cfg = norm["providers"][pid]
        env_map = ENV_BY_PROVIDER[pid]
        key_val = cfg.get("api_key") or ""
        if key_val:
            os.environ[env_map["api_key"]] = key_val
        else:
            os.environ.pop(env_map["api_key"], None)

        if pid == active:
            if cfg.get("model"):
                os.environ[env_map["model"]] = cfg["model"]
            if cfg.get("base_url"):
                os.environ[env_map["base_url"]] = cfg["base_url"]

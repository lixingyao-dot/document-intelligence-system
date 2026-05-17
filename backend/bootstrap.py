"""
桌面版启动引导：数据目录、环境变量、本地 settings.json → os.environ
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from backend.paths import ensure_sys_path, get_bundle_root, get_desktop_root, get_repo_src

ensure_sys_path()

def _settings_file() -> Path:
    override = os.environ.get("DOC_INTEL_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve() / "settings.json"
    return get_desktop_root() / "data" / "settings.json"


def get_data_dir() -> Path:
    override = os.environ.get("DOC_INTEL_DATA_DIR", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
    else:
        p = (get_desktop_root() / "data").resolve()
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("workspace", "workspace/library", "workspace/workflows", "temp", "temp/uploads", "output", "logs"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


def _apply_settings_to_env(settings: dict) -> None:
    from backend.settings_store import apply_settings_to_env

    apply_settings_to_env(settings)


def load_settings() -> dict:
    path = _settings_file()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict) -> None:
    from backend.settings_store import normalize_settings

    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_settings(data)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    _apply_settings_to_env(normalized)


def init_desktop_runtime() -> Path:
    """配置路径与环境，返回数据目录。须在 import api 之前调用。"""
    ensure_sys_path()
    data_dir = get_data_dir()

    os.environ.setdefault("DOC_INTEL_DESKTOP", "1")
    os.environ.setdefault("DOC_INTEL_ELECTRON", "1")
    os.environ["WORK_DIR"] = str(data_dir / "workspace")
    os.environ["OUTPUT_DIR"] = str(data_dir / "output")
    os.environ["TEMP_DIR"] = str(data_dir / "temp")

    from utils.desktop_runtime import lock_desktop_environment, reload_app_config

    lock_desktop_environment()

    settings = load_settings()
    _apply_settings_to_env(settings)

    lock_desktop_environment()
    reload_app_config()

    _seed_workspace_from_repo(data_dir)
    _seed_starter_workflows()
    return data_dir


def _seed_starter_workflows() -> None:
    """首次使用：写入若干示例工作流（普通 custom，非系统预设）。"""
    try:
        from starter_workflows import seed_starter_workflows_if_empty

        if seed_starter_workflows_if_empty():
            import logging

            logging.getLogger(__name__).info("已写入初始示例工作流")
    except Exception:
        pass


def _seed_workspace_from_repo(data_dir: Path) -> None:
    """首次运行：从打包资源或开发仓库复制工作流模板到本地 data/workspace。"""
    dest = data_dir / "workspace"
    marker = dest / "workflows" / "user_workflows.json"
    if marker.exists():
        return

    candidates = [
        get_bundle_root() / "workspace",
        get_repo_src() / "workspace",
        get_desktop_root() / "workspace",
        get_desktop_root() / "data" / "workspace",
    ]
    for src_ws in candidates:
        if src_ws.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copytree(
                    src_ws,
                    dest,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("user_workflows.json"),
                )
            except OSError:
                pass
            return

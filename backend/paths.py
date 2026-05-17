"""桌面版路径：兼容开发目录与 PyInstaller 打包后的 exe。"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_desktop_root() -> Path:
    """可写目录：exe 同级的 data/、日志等（开发时为 desktop-electron/）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_root() -> Path:
    """只读打包资源（前端 dist、内置 workspace 模板等）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", str(get_desktop_root())))
    return get_desktop_root()


def get_repo_src() -> Path:
    """业务 Python 包根（api、config、core…），位于 desktop-electron/src。"""
    if is_frozen():
        return get_bundle_root()
    return get_desktop_root() / "src"


def ensure_sys_path() -> None:
    root = get_desktop_root()
    bundle = get_bundle_root()
    src = get_repo_src()
    for p in (str(root), str(bundle), str(src)):
        if p not in sys.path:
            sys.path.insert(0, p)

"""
桌面版启动器：内嵌窗口 + 本进程 API（双击 exe 即完整应用，不打开系统浏览器）。

Electron 版由 server_entry.py 调用本模块；打包 API 时须包含 launcher（见 build_api.ps1）。
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", "")
    if _meipass and _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    _exe_dir = str(Path(sys.executable).resolve().parent)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)

from backend.paths import ensure_sys_path, get_desktop_root  # noqa: E402

ensure_sys_path()


def _is_electron_host() -> bool:
    return os.environ.get("DOC_INTEL_ELECTRON") == "1"


# 打包桌面 exe 时让 PyInstaller 分析到 pywebview（Electron API 包会排除该模块）
if getattr(sys, "frozen", False) and not _is_electron_host():
    try:
        import webview  # noqa: F401
        import webview.platforms.edgechromium  # noqa: F401
    except Exception:
        pass

_server_holder: dict = {"server": None}


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _wants_headless(args: argparse.Namespace) -> bool:
    return bool(args.headless or _is_electron_host())


def _pick_port(preferred: int = 8765) -> int:
    for port in (preferred, preferred + 1, preferred + 2, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port if port else s.getsockname()[1]
        except OSError:
            continue
    return preferred


def _resolve_port(args: argparse.Namespace) -> int:
    if args.port:
        return int(args.port)
    env_port = os.environ.get("DESKTOP_API_PORT", "").strip()
    if env_port.isdigit():
        return int(env_port)
    return _pick_port()


def _wait_health(port: int, timeout: float = 90.0) -> bool:
    import urllib.request

    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def _run_api_server(host: str, port: int) -> None:
    import uvicorn
    from backend.main import app

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    _server_holder["server"] = server
    server.run()


def _stop_api_server() -> None:
    server = _server_holder.get("server")
    if server is not None:
        server.should_exit = True


def _show_fatal_message(title: str, message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {message}", file=sys.stderr)


def _open_native_window(url: str) -> int:
    try:
        import webview  # noqa: F401
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        hint = (
            "当前为 Electron 专用 API 包（不含 pywebview）。\n"
            "请重新运行 desktop-electron\\scripts\\build_api.ps1 或 build.ps1 后，再启动 Electron 安装包。"
            if os.environ.get("DOC_INTEL_ELECTRON") == "1"
            else "请重新运行 scripts\\build_exe.ps1 打包；并确认已安装 WebView2 运行时。"
        )
        _show_fatal_message(
            "文档智能系统",
            f"无法加载内嵌窗口组件（pywebview）。\n{detail}\n\n{hint}",
        )
        return 1

    def on_closing() -> None:
        _stop_api_server()

    window = webview.create_window(
        "文档智能系统",
        url,
        width=1280,
        height=800,
        min_size=(900, 600),
    )
    window.events.closing += on_closing

    gui: Optional[str] = "edgechromium" if sys.platform == "win32" else None
    try:
        webview.start(gui=gui)
    except Exception as exc:
        if gui == "edgechromium":
            webview.start()
        else:
            _show_fatal_message(
                "文档智能系统",
                f"无法启动内嵌窗口：{type(exc).__name__}: {exc}\n\n请安装 Microsoft WebView2 运行时后重试。",
            )
            return 1
    _stop_api_server()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="文档智能系统 · 桌面本地版")
    parser.add_argument(
        "--external-browser",
        action="store_true",
        help="开发调试用：用系统浏览器打开（打包 exe 时忽略）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="仅启动 API，不打开窗口（Electron / server_entry 打包 API 使用）",
    )
    parser.add_argument("--port", type=int, default=0, help="0 表示自动选择端口")
    args = parser.parse_args()

    host = "127.0.0.1"
    port = _resolve_port(args)
    os.environ["DESKTOP_API_PORT"] = str(port)

    if _is_frozen() and _wants_headless(args):
        _run_api_server(host, port)
        return 0

    thread = threading.Thread(target=_run_api_server, args=(host, port), daemon=True)
    thread.start()

    if not _wait_health(port):
        timeout_hint = (
            "本地 API 启动超时。\n请重新运行 desktop-electron\\scripts\\build.ps1，"
            "或开发模式执行 desktop-electron\\scripts\\run_dev.ps1。"
            if _is_electron_host()
            else "服务启动超时。\n若刚更新代码，请重新运行 scripts\\build_exe.ps1。"
        )
        _show_fatal_message("文档智能系统", timeout_hint)
        return 1

    url = f"http://{host}:{port}/"
    data_dir = get_desktop_root() / "data"
    headless = _wants_headless(args)

    def _run_headless() -> int:
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            _stop_api_server()
        return 0

    if headless:
        return _run_headless()

    if _is_frozen():
        return _open_native_window(url)

    print(f"桌面版已启动: {url}")
    print(f"数据目录: {data_dir}")

    if args.external_browser:
        webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            _stop_api_server()
        return 0

    return _open_native_window(url)


if __name__ == "__main__":
    raise SystemExit(main())

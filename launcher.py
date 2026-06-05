"""
桌面版启动器：本进程 API（Electron 由 server_entry 以 headless 调用）。

打包 API 时须包含 launcher（见 build_api.ps1）。
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

if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", "")
    if _meipass and _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    _exe_dir = str(Path(sys.executable).resolve().parent)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)

from backend.paths import ensure_sys_path, get_desktop_root  # noqa: E402

ensure_sys_path()

_server_holder: dict = {"server": None}


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


def main() -> int:
    parser = argparse.ArgumentParser(description="文档智能系统 · 桌面本地版")
    parser.add_argument(
        "--external-browser",
        action="store_true",
        help="开发调试用：用系统浏览器打开",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="仅启动 API（Electron / server_entry 默认行为）",
    )
    parser.add_argument("--port", type=int, default=0, help="0 表示自动选择端口")
    args = parser.parse_args()

    host = "127.0.0.1"
    port = _resolve_port(args)
    os.environ["DESKTOP_API_PORT"] = str(port)

    headless = bool(
        args.headless
        or os.environ.get("DOC_INTEL_ELECTRON") == "1"
        or getattr(sys, "frozen", False)
    )

    if headless:
        _run_api_server(host, port)
        return 0

    thread = threading.Thread(target=_run_api_server, args=(host, port), daemon=True)
    thread.start()

    if not _wait_health(port):
        _show_fatal_message(
            "文档智能系统",
            "本地 API 启动超时。\n请运行 desktop-electron\\scripts\\run_dev.ps1 或 build.ps1。",
        )
        return 1

    url = f"http://{host}:{port}/"
    data_dir = get_desktop_root() / "data"
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


if __name__ == "__main__":
    raise SystemExit(main())

"""
仅启动本地 API（无 pywebview），供 Electron 主进程拉起。
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    argv = [sys.argv[0], *sys.argv[1:]]
    if "--headless" not in argv[1:]:
        argv.insert(1, "--headless")
    sys.argv = argv

    from launcher import main

    raise SystemExit(main())

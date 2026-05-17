#!/usr/bin/env python3
"""打包前检查：desktop-electron 能否导入 API 启动链上的关键模块。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src"

os.environ.setdefault("DOC_INTEL_DESKTOP", "1")
os.environ.setdefault("DOC_INTEL_ELECTRON", "1")
os.environ["DB_ENABLED"] = "false"

for p in (str(APP_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

CHECKS = [
    "launcher",
    "output",
    "output.result_handler",
    "backend.paths",
    "backend.bootstrap",
    "api.main",
    "core.orchestrator.coordinator",
    "core.agents.agent_b",
    "core.agents.agent_d",
    "service.agent_service",
    "starter_workflows",
    "workflow_storage",
]


def main() -> int:
    failed = []
    for name in CHECKS:
        try:
            __import__(name)
            print(f"  OK  {name}")
        except Exception as exc:
            print(f"  FAIL {name}: {exc}")
            failed.append(name)
    if failed:
        print(f"\n{len(failed)} import(s) failed. Fix src sync or requirements before PyInstaller.")
        return 1
    print("\nAll desktop import checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

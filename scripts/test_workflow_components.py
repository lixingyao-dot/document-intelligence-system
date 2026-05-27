#!/usr/bin/env python3
"""
后台批量测试工作流组件库（workflows_processors._process_node）。

  python scripts/test_workflow_components.py              # Mock LLM（默认）
  python scripts/test_workflow_components.py --live     # 真实 API（读环境变量）
  python scripts/test_workflow_components.py --live --model mimo-v2.5

环境变量（--live）:
  MIMO_API_KEY 或 OPENAI_API_KEY
  MIMO_BASE_URL（默认 https://token-plan-cn.xiaomimimo.com/v1）
  MIMO_MODEL（默认 mimo-v2.5-pro，须小写）
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src"
os.environ.setdefault("DOC_INTEL_DESKTOP", "1")
os.environ.setdefault("DOC_INTEL_ELECTRON", "1")
os.environ["DB_ENABLED"] = "false"
for p in (str(APP_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

DEFAULT_MIMO_BASE = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MIMO_MODEL = "mimo-v2.5-pro"

SAMPLE_TEXT = """# 测试文档
甲方：甲公司；乙方：乙公司。签署日期：2024-01-15。
项目金额：10000元。联系人手机：13812345678，邮箱：demo@example.com。
"""

ACTIVE_SCHEMAS = (
    "schema-translate",
    "schema-extract-summary",
    "schema-extract-data",
    "schema-entity-extraction",
    "schema-analyze-content",
    "schema-enhance-text",
    "schema-sensitive-masking",
    "schema-outline-generate",
)

RETIRED_SCHEMAS = (
    "schema-convert-format",
    "schema-split-document",
    "schema-keyword-highlight",
    "schema-term-normalize",
    "schema-sentiment-enhanced",
    "schema-timeline-extract",
    "schema-data-process",
    "schema-data-clean",
    "schema-table-extract",
    "schema-data-rollup",
)

COMPONENT_CASES: Dict[str, Tuple[Dict[str, Any], str, str]] = {
    "schema-translate": ({"targetLanguage": "en", "prompt": ""}, SAMPLE_TEXT, "sample.md"),
    "schema-extract-summary": (
        {"extractType": "summary", "summaryLength": "short", "prompt": ""},
        SAMPLE_TEXT,
        "sample.md",
    ),
    "schema-extract-data": (
        {"dataFormat": "json", "extractFields": "甲方,乙方,金额", "prompt": ""},
        SAMPLE_TEXT,
        "sample.md",
    ),
    "schema-analyze-content": (
        {"analysisType": "keywords", "topK": 5, "prompt": ""},
        SAMPLE_TEXT,
        "sample.md",
    ),
    "schema-enhance-text": (
        {"enhanceType": "polish", "style": "formal", "prompt": ""},
        SAMPLE_TEXT,
        "sample.md",
    ),
    "schema-sensitive-masking": ({"maskToken": "*", "prompt": ""}, SAMPLE_TEXT, "sample.md"),
    "schema-outline-generate": ({"maxDepth": 3, "prompt": ""}, SAMPLE_TEXT, "sample.md"),
    "schema-entity-extraction": (
        {
            "entityFieldList": "甲方\n乙方\n金额",
            "customEntityTypes": "",
            "aliasMap": "",
            "prompt": "",
        },
        SAMPLE_TEXT,
        "sample.md",
    ),
}


def _load_mimo_env_file() -> None:
    for name in ("mimo.local.env", ".mimo.local.env"):
        path = APP_ROOT / "scripts" / name
        if not path.exists():
            path = APP_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _apply_live_llm_env(model: str) -> str:
    _load_mimo_env_file()
    api_key = (
        os.environ.get("MIMO_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        raise SystemExit(
            "缺少 API Key：设置 MIMO_API_KEY 或 OPENAI_API_KEY，"
            "或复制 scripts/mimo.env.example → scripts/mimo.local.env"
        )
    base = os.environ.get("MIMO_BASE_URL", DEFAULT_MIMO_BASE).strip() or DEFAULT_MIMO_BASE
    model = (model or os.environ.get("MIMO_MODEL", DEFAULT_MIMO_MODEL)).strip().lower()

    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_BASE_URL"] = base
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL"] = model
    os.environ["OPENAI_BASE_URL"] = base
    return model


def _prepare_live_config():
    from config import load_config, set_config
    from core.llm.llm_service import reset_llm_service

    cfg = load_config()
    cfg.llm.streaming = False
    cfg.llm.temperature = 0.3
    cfg.llm.max_tokens = 2048
    cfg.llm.request_timeout_seconds = 120.0
    set_config(cfg)
    reset_llm_service()


class _MockLLM:
    def chat(self, messages, temperature=0.3, strip_markdown_output=False, **kwargs):
        user = ""
        for m in messages or []:
            if isinstance(m, dict) and m.get("role") == "user":
                user = str(m.get("content") or "")
        if "翻译" in user:
            return "[MOCK_TRANSLATED]\n" + user[-120:]
        if "JSON" in user:
            return '{"mock": true}'
        if "脱敏" in user:
            return "手机：138****5678"
        return "[MOCK_OK]\n" + user[:200]


def _mock_get_llm_service():
    return _MockLLM()


def _run_case(
    process_node: Callable,
    schema_key: str,
    config: Dict[str, Any],
    content: str,
    file_name: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    from config import get_config

    node = SimpleNamespace(
        type="ai",
        title=schema_key,
        schemaKey=schema_key,
        configValues=config,
    )
    t0 = time.perf_counter()
    try:
        out = process_node(content, file_name, node, get_config(), {})
    except Exception as exc:
        return "fail", str(exc), None
    elapsed = time.perf_counter() - t0

    if out is None or not str(out).strip():
        return "fail", "空输出", None
    out_s = str(out).strip()
    if out_s == content.strip():
        return "weak", "输出与输入相同", out_s[:160]
    return "ok", f"{elapsed:.1f}s", out_s[:160]


def _ping_llm() -> None:
    from core.llm.llm_service import get_llm_service
    from config import get_config

    svc = get_llm_service()
    cfg = get_config().llm
    print(f"  provider={cfg.provider} model={cfg.model}")
    print(f"  base_url={cfg.base_url}")
    text = svc.chat(
        [{"role": "user", "content": "回复 OK 两个字母即可"}],
        strip_markdown_output=False,
    )
    print(f"  ping: {(text or '')[:80]!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="工作流组件库后台测试")
    parser.add_argument("--live", action="store_true", help="使用真实 MiMo / OpenAI 兼容 API")
    parser.add_argument("--model", default="", help="模型名（小写），默认 mimo-v2.5-pro")
    parser.add_argument("--ping-only", action="store_true", help="仅测连通性")
    args = parser.parse_args()

    import api.routers.workflows_processors as wp

    mode = "live" if args.live else "mock"
    model_name = ""
    if args.live:
        model_name = _apply_live_llm_env(args.model)
        _prepare_live_config()
        print(f"=== 真实 API 测试 · {model_name} ===\n")
        try:
            _ping_llm()
        except Exception as exc:
            print(f"连通失败: {exc}")
            return 1
        if args.ping_only:
            return 0
        print()
    else:
        wp._get_llm_service = _mock_get_llm_service  # type: ignore
        print("=== Mock LLM 测试 ===\n")

    ok: List[str] = []
    weak: List[Tuple[str, str, str]] = []
    fail: List[Tuple[str, str]] = []

    for schema_key in ACTIVE_SCHEMAS:
        config, content, fname = COMPONENT_CASES[schema_key]
        status, detail, preview = _run_case(wp._process_node, schema_key, config, content, fname)
        label = schema_key
        if status == "ok":
            ok.append(f"{label} ({detail})")
            print(f"  OK   {label}  {detail}")
            if preview and args.live:
                print(f"       → {preview[:100]}...")
        elif status == "weak":
            weak.append((label, detail or "", preview or ""))
            print(f"  WEAK {label}  {detail}")
        else:
            fail.append((label, detail or ""))
            print(f"  FAIL {label}  {detail}")

    print(f"\n通过 {len(ok)}/{len(ACTIVE_SCHEMAS)}")
    if weak:
        print("弱效果:", [w[0] for w in weak])
    if fail:
        print("失败:", fail)
        return 1

    if not args.live:
        retired_ok = 0
        from config import get_config

        for schema_key in RETIRED_SCHEMAS:
            node = SimpleNamespace(
                type="ai",
                title=schema_key,
                schemaKey=schema_key,
                configValues={},
            )
            out = wp._process_node("原文", "x.md", node, get_config(), {})
            if out == "原文":
                retired_ok += 1
        print(f"下架组件透传 {retired_ok}/{len(RETIRED_SCHEMAS)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

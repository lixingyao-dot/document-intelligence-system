#!/usr/bin/env python3
"""
课堂演示三样例端到端测试（提取与填表）。

环境变量（勿写入仓库）:
  MIMO_API_KEY / LLM_PROVIDER=mimo / MIMO_MODEL / MIMO_BASE_URL
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src"
OUT = APP_ROOT / "output" / "demo_classroom"
os.environ.setdefault("DOC_INTEL_DESKTOP", "1")
os.environ.setdefault("DOC_INTEL_ELECTRON", "1")
os.environ["DB_ENABLED"] = "false"

for p in (str(APP_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.bootstrap import init_desktop_runtime  # noqa: E402

init_desktop_runtime()

from config import get_config, load_config, set_config  # noqa: E402  # after bootstrap
from core.agents.agent_b import AgentB  # noqa: E402
from core.agents.agent_c import run_agent_c_api, run_agent_c_fill_from_entities  # noqa: E402
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType  # noqa: E402


def _demo_root() -> Path:
    return next(p for p in APP_ROOT.iterdir() if p.is_dir() and (p / "README.txt").exists())


def _read_prompt(sub: Path) -> str:
    p = sub / "用户要求.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _classify(sub: Path) -> str:
    docx = list(sub.glob("*.docx"))
    xlsx = list(sub.glob("*.xlsx"))
    has_covid = any("covid" in f.name.lower() for f in docx + xlsx)
    if has_covid:
        return "covid"
    tpl_docx = [f for f in docx if "模板" in f.name]
    tpl_xlsx = [f for f in xlsx if "模板" in f.name]
    data_docx = [f for f in docx if "模板" not in f.name]
    data_xlsx = [f for f in xlsx if "模板" not in f.name]
    if tpl_docx and data_xlsx:
        return "shandong"
    if tpl_xlsx and data_docx:
        return "city_gdp"
    return "unknown"


def _apply_llm_env() -> None:
    """在 bootstrap 加载 settings.json 之后强制切到 MiMo（避免被智谱等旧配置覆盖）。"""
    from backend.settings_store import apply_settings_to_env
    from utils.desktop_runtime import reload_app_config

    key = os.getenv("MIMO_API_KEY", "").strip()
    if not key:
        set_config(load_config())
        return

    model = os.getenv("MIMO_MODEL", "mimo-v2.5").strip()
    base = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1").strip()
    apply_settings_to_env(
        {
            "active_provider": "mimo",
            "providers": {
                "mimo": {"model": model, "base_url": base, "api_key": key},
            },
        }
    )
    reload_app_config()
    set_config(load_config())


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def test_shandong(sub: Path, out: Path) -> None:
    print("\n[1] 山东空气质量 · Excel → Word 多表")
    prompt = _read_prompt(sub)
    data_xlsx = next(f for f in sub.glob("*.xlsx") if "模板" not in f.name)
    tpl_docx = next(f for f in sub.glob("*.docx") if "模板" in f.name)
    result = run_agent_c_api(
        src=str(data_xlsx),
        prompt=prompt,
        template=str(tpl_docx),
        output_template=str(out / "shandong_filled.docx"),
        allow_rule_fallback=True,
    )
    if not result.get("success"):
        _fail(result.get("message", "unknown"))
    data = result.get("data") or {}
    multi = data.get("multi_table_results") or []
    if len(multi) < 3:
        _fail(f"期望 3 张表结果，实际 {len(multi)}")
    for t in multi:
        if int(t.get("matched_rows") or 0) < 1:
            _fail(f"{t.get('name')} 命中 0 行")
    _ok(f"多表填表 {len(multi)} 表，总命中 {data.get('matched_rows')} 行 → {data.get('template_output')}")


def test_city_gdp(sub: Path, out: Path) -> None:
    print("\n[2] 百强城市 · Word → Excel")
    prompt = _read_prompt(sub) or "填入表格"
    data_docx = next(f for f in sub.glob("*.docx") if "模板" not in f.name)
    tpl_xlsx = next(f for f in sub.glob("*.xlsx") if "模板" in f.name)

    task = TaskSpec(
        task_type=TaskType.ENTITY_EXTRACTION,
        instruction=prompt,
        source_files=[FileInfo(path=str(data_docx), file_type=FileType.DOCX, name=data_docx.name)],
        template_file=FileInfo(path=str(tpl_xlsx), file_type=FileType.XLSX, name=tpl_xlsx.name),
    )
    agent = AgentB(load_config())
    resp = agent.execute(task)
    if not resp.success:
        _fail(resp.message)
    data = resp.data or {}
    extract_source = str(data.get("extract_source") or "")
    if extract_source != "llm":
        _fail(f"期望大模型提取 extract_source=llm，实际 {extract_source!r}；message={resp.message}")
    entities = data.get("entities") or []
    if len(entities) < 10:
        _fail(f"实体过少: {len(entities)}（大模型未提取足够城市）")
    fill = run_agent_c_fill_from_entities(
        entities=entities,
        template=str(tpl_xlsx),
        output_template=str(out / "city_gdp_filled.xlsx"),
        output_json=str(out / "city_gdp_entities.json"),
    )
    if not fill.get("success"):
        _fail(fill.get("message", "填表失败"))
    matched = int((fill.get("data") or {}).get("matched_rows") or 0)
    if matched < 10:
        _fail(f"填表行数过少: {matched}")
    _ok(f"提取 {len(entities)} 条，写入 {matched} 行 → {(fill.get('data') or {}).get('template_output')}")


def test_covid(sub: Path, out: Path) -> None:
    print("\n[3] COVID · Excel 日期筛选 → Excel 模板")
    prompt = _read_prompt(sub)
    data_xlsx = next(f for f in sub.glob("*.xlsx") if "模板" not in f.name)
    tpl_xlsx = next(f for f in sub.glob("*.xlsx") if "模板" in f.name)
    result = run_agent_c_api(
        src=str(data_xlsx),
        prompt=prompt,
        template=str(tpl_xlsx),
        output_template=str(out / "covid_filled.xlsx"),
        allow_rule_fallback=True,
    )
    if not result.get("success"):
        _fail(result.get("message", "unknown"))
    matched = int((result.get("data") or {}).get("matched_rows") or 0)
    if matched < 1:
        _fail("日期筛选命中 0 行")
    _ok(f"命中 {matched} 行 → {(result.get('data') or {}).get('template_output')}")


def main() -> int:
    _apply_llm_env()
    cfg = get_config()
    print("LLM:", cfg.llm.provider, cfg.llm.model, "key=", bool(cfg.llm.api_key))

    root = _demo_root()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = {}
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        kind = _classify(sub)
        if kind != "unknown":
            cases[kind] = sub

    for need in ("shandong", "city_gdp", "covid"):
        if need not in cases:
            _fail(f"缺少样例目录: {need}")

    test_shandong(cases["shandong"], OUT)
    test_city_gdp(cases["city_gdp"], OUT)
    test_covid(cases["covid"], OUT)

    summary = OUT / "summary.json"
    summary.write_text(
        json.dumps({"status": "ok", "output_dir": str(OUT)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n全部通过。输出目录: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

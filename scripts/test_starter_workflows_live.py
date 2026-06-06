#!/usr/bin/env python3
"""
逐个测试 8 个预设工作流组件（真实 LLM API）。

用法：
  python scripts/test_starter_workflows_live.py
  python scripts/test_starter_workflows_live.py --component translate
  python scripts/test_starter_workflows_live.py --component summary --verbose
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time

# Windows 终端 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src"
FIXTURES = APP_ROOT / "test-fixtures"
os.environ["DOC_INTEL_DESKTOP"] = "1"
os.environ["DOC_INTEL_ELECTRON"] = "1"
os.environ["DB_ENABLED"] = "false"
for p in (str(APP_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── API 配置 ──────────────────────────────────────────────────
API_KEY = os.environ.get("MIMO_API_KEY", "tp-cu1bua4adq2hgiko6pbiyvbw2ab6bp14jhm286fhgxgnv3ch")
BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5")

# ── 8 组件 → (fixture_dir, 文件名, schemaKey, configValues) ──
COMPONENT_TESTS: Dict[str, Dict[str, Any]] = {
    "translate": {
        "name": "AI 翻译",
        "fixture_dir": "ai-translate",
        "file": "国际贸易合同范本_电子产品出口协议.txt",
        "schema": "schema-translate",
        "config": {
            "targetLanguage": "zh",
            "prompt": (
                "你是一位专业翻译。请将以下文档全文翻译为{target_language}。\n"
                "要求：\n"
                "1. 保持原文的段落、标题、列表等 Markdown 结构不变；\n"
                "2. 专业术语首次出现时在括号内附上原文；\n"
                "3. 数字、日期、单位按目标语言习惯格式化；\n"
                "4. 仅输出译文，禁止添加任何解释或注释。"
            ),
        },
    },
    "summary": {
        "name": "内容提取",
        "fixture_dir": "content-extract",
        "file": "企业数字化转型实施方案_完整版.txt",
        "schema": "schema-extract-summary",
        "config": {
            "extractType": "both",
            "summaryLength": "medium",
            "prompt": (
                "请对以下文档进行内容提取，输出两部分：\n\n"
                "## 摘要\n用 3-5 句话概括文档的核心主题、主要论点和结论。\n\n"
                "## 关键要点\n以编号列表形式列出 5-8 条最重要的信息点，每条不超过 30 字。"
            ),
        },
    },
    "data": {
        "name": "数据抽取",
        "fixture_dir": "data-extract",
        "file": "2024年度华南区财务审计报告.txt",
        "schema": "schema-extract-data",
        "config": {
            "dataFormat": "json",
            "extractFields": "名称,日期,金额",
            "prompt": (
                "请从文档中抽取结构化数据，规则如下：\n"
                "1. 逐条提取包含以下字段的记录：名称、日期、金额；\n"
                "2. 日期统一为 YYYY-MM-DD 格式；\n"
                "3. 金额保留两位小数，带货币符号；\n"
                "4. 若某字段在原文中不存在，填 null；\n"
                "5. 仅输出 JSON 数组，不要其他文字。"
            ),
        },
    },
    "entity": {
        "name": "实体提取",
        "fixture_dir": "entity-extract",
        "file": "2025年全国两会政府工作报告摘要.txt",
        "schema": "schema-entity-extraction",
        "config": {
            "entityFieldList": "人名\n日期\n金额\n机构名称",
            "customEntityTypes": "政策名称、重大项目",
            "aliasMap": "",
            "prompt": (
                "请从文档中逐段抽取结构化实体，规则：\n"
                "1. 按字段列表提取每个字段对应的值；\n"
                "2. 同时识别自定义实体类型（政策名称、重大项目）；\n"
                "3. 日期格式统一为 YYYY-MM-DD；\n"
                "4. 输出 JSON 对象，结构：{entities: [...], customEntities: [...]}。"
            ),
        },
    },
    "analyze": {
        "name": "内容分析",
        "fixture_dir": "content-analyze",
        "file": "2024年中国新能源汽车用户满意度调查报告.txt",
        "schema": "schema-analyze-content",
        "config": {
            "analysisType": "all",
            "entityTypes": ["person", "location", "org", "date"],
            "topK": "10",
            "prompt": (
                "请对以下文档进行全面分析，输出三部分：\n\n"
                "## 关键词\n提取 10 个最重要的关键词，按重要性降序排列。\n\n"
                "## 实体识别\n分类列出人名、地名、机构、日期。\n\n"
                "## 文档主题\n用一句话总结文档主题。"
            ),
        },
    },
    "enhance": {
        "name": "文本增强",
        "fixture_dir": "text-enhance",
        "file": "产品发布新闻稿初稿_智能文档助手3.0.txt",
        "schema": "schema-enhance-text",
        "config": {
            "enhanceType": "all",
            "style": "professional",
            "prompt": (
                "请对以下文本进行全面优化：\n"
                "### 1. 语法检查\n修正错别字、标点符号错误和语法问题。\n\n"
                "### 2. 文本润色\n提升表达的流畅度和专业性。\n\n"
                "### 3. 改写\n对重点段落进行改写，使逻辑更清晰。\n\n"
                "请直接输出优化后的完整文本。"
            ),
        },
    },
    "masking": {
        "name": "敏感信息脱敏",
        "fixture_dir": "sensitive-desensitize",
        "file": "员工人事档案信息表.txt",
        "schema": "schema-sensitive-masking",
        "config": {
            "maskToken": "*",
            "prompt": (
                "请对以下文档中的敏感信息进行脱敏处理，规则：\n"
                "1. 手机号码：保留前 3 位和后 4 位，中间用 **** 替换；\n"
                "2. 身份证号：保留前 4 位和后 4 位，中间用 ****** 替换；\n"
                "3. 邮箱地址：用户名部分保留首字符，其余用 *** 替换；\n"
                "4. 银行卡号：仅保留后 4 位；\n"
                "5. 详细地址：保留省/市级，具体街道替换为「***」；\n"
                "6. 人名：保留姓，名替换为「**」。\n"
                "保持文档原有格式不变，仅替换敏感内容。"
            ),
        },
    },
    "outline": {
        "name": "结构化提纲生成",
        "fixture_dir": "outline-generate",
        "file": "人工智能赋能教育现代化白皮书.txt",
        "schema": "schema-outline-generate",
        "config": {
            "maxDepth": "3",
            "prompt": (
                "请根据文档内容生成结构化提纲，要求：\n"
                "1. 最多 3 级层级；\n"
                "2. 每个提纲项不超过 20 字；\n"
                "3. 同级标题保持逻辑并列；\n"
                "4. 标题使用名词短语或动宾结构；\n"
                "5. 按文档原有顺序排列。"
            ),
        },
    },
}


def _setup_live_llm():
    """配置真实 LLM 环境并重置服务。"""
    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["LLM_MODEL"] = MODEL
    os.environ["LLM_BASE_URL"] = BASE_URL
    os.environ["OPENAI_API_KEY"] = API_KEY
    os.environ["OPENAI_MODEL"] = MODEL
    os.environ["OPENAI_BASE_URL"] = BASE_URL

    from config import load_config, set_config
    from core.llm.llm_service import reset_llm_service

    cfg = load_config()
    cfg.llm.streaming = False
    cfg.llm.temperature = 0.3
    cfg.llm.max_tokens = 4096
    cfg.llm.request_timeout_seconds = 120.0
    set_config(cfg)
    reset_llm_service()


def _read_fixture(fixture_dir: str, file_name: str) -> str:
    path = FIXTURES / fixture_dir / file_name
    if not path.exists():
        raise FileNotFoundError(f"测试文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def _run_component(
    schema_key: str,
    config_values: Dict[str, Any],
    content: str,
    file_name: str,
    verbose: bool = False,
) -> Tuple[str, str, str, float]:
    """执行单个组件，返回 (status, detail, output_preview, elapsed)。"""
    from config import get_config
    from api.routers.workflows_processors import _process_node

    node = SimpleNamespace(
        type="ai",
        title=schema_key,
        schemaKey=schema_key,
        configValues=config_values,
    )
    t0 = time.perf_counter()
    try:
        out = _process_node(content, file_name, node, get_config(), {})
    except Exception as exc:
        return "FAIL", str(exc), "", time.perf_counter() - t0
    elapsed = time.perf_counter() - t0

    if out is None or not str(out).strip():
        return "FAIL", "空输出", "", elapsed

    out_s = str(out).strip()
    in_s = content.strip()
    if out_s == in_s:
        return "WEAK", "输出与输入完全相同", out_s[:200], elapsed

    return "OK", f"{elapsed:.1f}s len={len(out_s)}", out_s[:500], elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="预设工作流实时 API 测试")
    parser.add_argument("--component", "-c", default="",
                        help="仅测试指定组件 (translate/summary/data/entity/analyze/enhance/masking/outline)")
    parser.add_argument("--verbose", "-v", action="store_true", help="输出完整预览")
    parser.add_argument("--save", "-s", action="store_true", help="将输出保存到 test-fixtures/_output/")
    args = parser.parse_args()

    _setup_live_llm()

    # 连通性测试
    from core.llm.llm_service import get_llm_service
    svc = get_llm_service()
    print(f"模型: {MODEL} @ {BASE_URL}")
    try:
        ping = svc.chat([{"role": "user", "content": "回复 OK"}], strip_markdown_output=False)
        print(f"连通性: {(ping or '')[:60]!r}")
    except Exception as exc:
        print(f"连通失败: {exc}")
        return 1
    print()

    targets = COMPONENT_TESTS
    if args.component:
        key = args.component.lower()
        if key not in COMPONENT_TESTS:
            print(f"未知组件: {key}，可选: {', '.join(COMPONENT_TESTS.keys())}")
            return 1
        targets = {key: COMPONENT_TESTS[key]}

    out_dir = APP_ROOT / "test-fixtures" / "_output"
    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)

    ok_list, weak_list, fail_list = [], [], []
    total_time = 0.0

    for key, spec in targets.items():
        label = f"[{key}] {spec['name']}"
        print(f"{'='*60}")
        print(f"  测试: {label}")
        print(f"  文件: {spec['file']}")
        print(f"  Schema: {spec['schema']}")

        content = _read_fixture(spec["fixture_dir"], spec["file"])
        print(f"  输入长度: {len(content)} 字符")

        status, detail, preview, elapsed = _run_component(
            spec["schema"], spec["config"], content, spec["file"], args.verbose
        )
        total_time += elapsed

        if status == "OK":
            ok_list.append(label)
            print(f"  结果: ✅ {detail}")
        elif status == "WEAK":
            weak_list.append((label, detail))
            print(f"  结果: ⚠️  {detail}")
        else:
            fail_list.append((label, detail))
            print(f"  结果: ❌ {detail}")

        if preview:
            print(f"  预览:")
            for line in preview.split("\n")[:15]:
                print(f"    {line}")
            if len(preview) > 500:
                print(f"    ...(截断)")

        if args.save and status in ("OK", "WEAK"):
            save_path = out_dir / f"{key}_output.txt"
            save_path.write_text(preview, encoding="utf-8")
            print(f"  已保存: {save_path}")

        print()

    # ── 汇总 ──────────────────────────────────────────────────
    total = len(targets)
    print("=" * 60)
    print(f"  测试完成 · 总耗时 {total_time:.1f}s")
    print(f"  ✅ 通过: {len(ok_list)}/{total}")
    if weak_list:
        print(f"  ⚠️  弱效果: {[w[0] for w in weak_list]}")
    if fail_list:
        print(f"  ❌ 失败: {[(f[0], f[1]) for f in fail_list]}")
    print("=" * 60)

    return 1 if fail_list else 0


if __name__ == "__main__":
    raise SystemExit(main())

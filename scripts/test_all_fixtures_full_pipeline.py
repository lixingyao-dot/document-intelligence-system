#!/usr/bin/env python3
"""
完整工作流流水线测试：遍历 test-fixtures 所有文件，走 execute_workflow_pipeline 全流程。

流程：读取文件 → TaskSpec(WORKFLOW_PIPELINE) → WorkflowCoordinator.execute → 输出文件
与前端点击「执行」按钮走的是同一条代码路径。

用法：
  python scripts/test_all_fixtures_full_pipeline.py
  python scripts/test_all_fixtures_full_pipeline.py --dry-run   # 仅打印计划，不实际调用 LLM
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src"
FIXTURES = APP_ROOT / "test-fixtures"
OUTPUT_DIR = APP_ROOT / "test-fixtures" / "_pipeline_output"

os.environ["DOC_INTEL_DESKTOP"] = "1"
os.environ["DOC_INTEL_ELECTRON"] = "1"
os.environ["DB_ENABLED"] = "false"
for p in (str(APP_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── fixture 目录 → 预设工作流映射 ────────────────────────────
# 每个目录对应 starter_workflows.py 中的一个工作流
FIXTURE_WORKFLOW_MAP: Dict[str, Dict[str, Any]] = {
    "ai-translate": {
        "workflow_name": "AI 翻译流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_ai_translate",
            "type": "ai",
            "title": "AI 翻译",
            "schemaKey": "schema-translate",
            "configValues": {
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
        "output_format": "md",
        "naming_suffix": "translated",
    },
    "content-extract": {
        "workflow_name": "内容提取流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_extract",
            "type": "ai",
            "title": "内容提取",
            "schemaKey": "schema-extract-summary",
            "configValues": {
                "extractType": "both",
                "summaryLength": "medium",
                "prompt": (
                    "请对以下文档进行内容提取，输出两部分：\n\n"
                    "## 摘要\n用 3-5 句话概括文档的核心主题、主要论点和结论。\n\n"
                    "## 关键要点\n以编号列表形式列出 5-8 条最重要的信息点，每条不超过 30 字。"
                ),
            },
        },
        "output_format": "md",
        "naming_suffix": "summary",
    },
    "data-extract": {
        "workflow_name": "数据抽取流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_data_extract",
            "type": "ai",
            "title": "数据抽取",
            "schemaKey": "schema-extract-data",
            "configValues": {
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
        "output_format": "json",
        "naming_suffix": "data",
    },
    "entity-extract": {
        "workflow_name": "实体提取流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_entity",
            "type": "ai",
            "title": "实体提取",
            "schemaKey": "schema-entity-extraction",
            "configValues": {
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
        "output_format": "json",
        "naming_suffix": "entities",
    },
    "content-analyze": {
        "workflow_name": "内容分析流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_analyze",
            "type": "ai",
            "title": "内容分析",
            "schemaKey": "schema-analyze-content",
            "configValues": {
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
        "output_format": "md",
        "naming_suffix": "analysis",
    },
    "text-enhance": {
        "workflow_name": "文本增强流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_enhance",
            "type": "ai",
            "title": "文本增强",
            "schemaKey": "schema-enhance-text",
            "configValues": {
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
        "output_format": "md",
        "naming_suffix": "enhanced",
    },
    "sensitive-desensitize": {
        "workflow_name": "敏感信息脱敏流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_masking",
            "type": "ai",
            "title": "敏感信息脱敏",
            "schemaKey": "schema-sensitive-masking",
            "configValues": {
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
        "output_format": "md",
        "naming_suffix": "masked",
    },
    "outline-generate": {
        "workflow_name": "提纲生成流",
        "input_kind": "txt",
        "middle_node": {
            "id": "n_outline",
            "type": "ai",
            "title": "结构化提纲生成",
            "schemaKey": "schema-outline-generate",
            "configValues": {
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
        "output_format": "md",
        "naming_suffix": "outline",
    },
}


def _setup_live_llm():
    api_key = os.environ.get("MIMO_API_KEY", "tp-cu1bua4adq2hgiko6pbiyvbw2ab6bp14jhm286fhgxgnv3ch")
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5")

    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_BASE_URL"] = base_url
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL"] = model
    os.environ["OPENAI_BASE_URL"] = base_url

    from config import load_config, set_config
    from core.llm.llm_service import reset_llm_service

    cfg = load_config()
    cfg.llm.streaming = False
    cfg.llm.temperature = 0.3
    cfg.llm.max_tokens = 4096
    cfg.llm.request_timeout_seconds = 180.0
    set_config(cfg)
    reset_llm_service()

    return model


def _build_nodes(workflow_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """构建完整工作流节点列表：输入 → 中间 → 输出。"""
    mid = workflow_spec["middle_node"]
    return [
        {
            "id": "n_in",
            "type": "input",
            "title": "文档输入",
            "schemaKey": "schema-document-input",
            "configValues": {
                "inputFileKind": workflow_spec["input_kind"],
                "inputSource": "library",
                "spaceId": None,
                "skipExisting": False,
            },
        },
        mid,
        {
            "id": "n_out",
            "type": "output",
            "title": "文档输出",
            "schemaKey": "schema-library-output",
            "configValues": {
                "outputMode": "external",
                "savePath": str(OUTPUT_DIR),
                "namingRule": f"{{original_name}}_{workflow_spec['naming_suffix']}",
                "outputFormat": workflow_spec["output_format"],
            },
        },
    ]


def _run_single_file(
    file_path: Path,
    workflow_spec: Dict[str, Any],
    config,
) -> Tuple[str, str, float]:
    """
    对单个文件走完整工作流流水线。
    返回 (status, detail, elapsed_seconds)
    """
    from core.orchestrator.coordinator import WorkflowCoordinator
    from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType

    nodes = _build_nodes(workflow_spec)
    file_type = FileType.TXT

    task_spec = TaskSpec(
        task_type=TaskType.WORKFLOW_PIPELINE,
        instruction=f"workflow:test_{workflow_spec['naming_suffix']}",
        source_files=[FileInfo(path=str(file_path), file_type=file_type, name=file_path.name)],
        parameters={
            "workflow_nodes": nodes,
            "output_config": {
                "outputMode": "external",
                "outputFormat": workflow_spec["output_format"],
                "savePath": str(OUTPUT_DIR),
                "namingRule": f"{{original_name}}_{workflow_spec['naming_suffix']}",
            },
            "input_config": {"inputFileKind": "txt", "skipExisting": False},
            "execution_id": f"test_{workflow_spec['naming_suffix']}_{file_path.stem}",
        },
    )

    def _progress(progress, total, message, **kwargs):
        pass  # 静默进度

    coordinator = WorkflowCoordinator(config)
    t0 = time.perf_counter()
    try:
        result = coordinator.execute(task_spec, progress_callback=_progress)
        elapsed = time.perf_counter() - t0
        if not result.success:
            return "FAIL", result.message, elapsed

        # 检查输出文件是否生成
        output_file = result.output_file
        if output_file and Path(output_file).exists():
            size = Path(output_file).stat().st_size
            return "OK", f"{elapsed:.1f}s → {Path(output_file).name} ({size}B)", elapsed

        # 检查 data 中的输出
        data = result.data
        if isinstance(data, dict):
            out = data.get("output", {})
            out_path = out.get("path") if isinstance(out, dict) else None
            if out_path and Path(out_path).exists():
                size = Path(out_path).stat().st_size
                return "OK", f"{elapsed:.1f}s → {Path(out_path).name} ({size}B)", elapsed

        return "WARN", f"{elapsed:.1f}s 完成但未找到输出文件", elapsed

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return "FAIL", f"{elapsed:.1f}s {exc}", elapsed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="全量工作流流水线测试")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划")
    parser.add_argument("--component", "-c", default="", help="仅测试指定目录")
    args = parser.parse_args()

    # 收集所有待测文件
    test_plan: List[Tuple[str, Path]] = []  # (fixture_dir, file_path)
    dirs = FIXTURE_WORKFLOW_MAP
    if args.component:
        key = args.component
        if key not in dirs:
            print(f"未知目录: {key}，可选: {', '.join(dirs.keys())}")
            return 1
        dirs = {key: FIXTURE_WORKFLOW_MAP[key]}

    for dir_name in dirs:
        dir_path = FIXTURES / dir_name
        if not dir_path.exists():
            print(f"目录不存在: {dir_path}")
            continue
        for f in sorted(dir_path.glob("*.txt")):
            test_plan.append((dir_name, f))

    total = len(test_plan)
    print(f"共 {total} 个文件待测，涉及 {len(dirs)} 个工作流\n")

    if args.dry_run:
        for dir_name, fp in test_plan:
            spec = FIXTURE_WORKFLOW_MAP[dir_name]
            print(f"  [{dir_name}] {spec['middle_node']['schemaKey']:30s} → {fp.name}")
        return 0

    # 初始化 LLM
    model = _setup_live_llm()
    from core.llm.llm_service import get_llm_service
    from config import get_config

    svc = get_llm_service()
    print(f"模型: {model}")
    try:
        ping = svc.chat([{"role": "user", "content": "回复 OK"}], strip_markdown_output=False)
        print(f"连通: {(ping or '')[:40]!r}")
    except Exception as exc:
        print(f"连通失败: {exc}")
        return 1

    # 清理输出目录
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = get_config()
    ok_list: List[str] = []
    warn_list: List[Tuple[str, str]] = []
    fail_list: List[Tuple[str, str]] = []
    total_time = 0.0

    for idx, (dir_name, file_path) in enumerate(test_plan, 1):
        spec = FIXTURE_WORKFLOW_MAP[dir_name]
        schema = spec["middle_node"]["schemaKey"]
        label = f"[{dir_name}] {file_path.name}"

        print(f"[{idx}/{total}] {label}")
        print(f"        schema={schema}  format={spec['output_format']}")

        status, detail, elapsed = _run_single_file(file_path, spec, config)
        total_time += elapsed

        if status == "OK":
            ok_list.append(label)
            print(f"        ✅ {detail}")
        elif status == "WARN":
            warn_list.append((label, detail))
            print(f"        ⚠️  {detail}")
        else:
            fail_list.append((label, detail))
            print(f"        ❌ {detail}")
        print()

    # ── 汇总 ──────────────────────────────────────────────────
    print("=" * 70)
    print(f"  全量流水线测试完成")
    print(f"  总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  ✅ 通过: {len(ok_list)}/{total}")
    if warn_list:
        print(f"  ⚠️  警告: {len(warn_list)}")
        for w in warn_list:
            print(f"      {w[0]}: {w[1]}")
    if fail_list:
        print(f"  ❌ 失败: {len(fail_list)}")
        for f in fail_list:
            print(f"      {f[0]}: {f[1]}")
    print("=" * 70)

    # 列出输出文件
    out_files = sorted(OUTPUT_DIR.glob("*"))
    if out_files:
        print(f"\n输出目录: {OUTPUT_DIR}")
        for f in out_files:
            print(f"  {f.name:50s} {f.stat().st_size:>8,d} B")

    return 1 if fail_list else 0


if __name__ == "__main__":
    raise SystemExit(main())

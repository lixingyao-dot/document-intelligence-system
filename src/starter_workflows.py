"""
首次使用（工作流列表为空）时写入的示例工作流。
8 个组件各一个预设工作流，覆盖全部中间节点类型。
均为 type=custom，与用户自建工作流相同，可编辑、保存、删除。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import SystemConfig, get_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _input_node() -> dict:
    """通用输入节点模板，默认支持所有格式。"""
    return {
        "id": "n_doc_input",
        "type": "input",
        "title": "文档输入",
        "body": "选择源文件格式与文档来源",
        "schemaKey": "schema-document-input",
        "configValues": {
            "inputFileKinds": ["pdf", "txt", "md", "docx", "xlsx"],
            "inputSource": "library",
            "spaceId": None,
            "skipExisting": False,
        },
    }


def _output_node(naming_suffix: str, output_format: str = "pdf") -> dict:
    """通用输出节点模板。"""
    return {
        "id": "n_output",
        "type": "output",
        "title": "文档输出",
        "body": "选择输出文档库与导出格式",
        "schemaKey": "schema-library-output",
        "configValues": {
            "outputMode": "library",
            "targetSpaceId": None,
            "namingRule": f"{{original_name}}_{naming_suffix}",
            "outputFormat": output_format,
        },
    }


def build_starter_workflows(now: Optional[str] = None) -> Dict[str, Any]:
    ts = now or _utc_now()

    # ── 1. AI 翻译 ─────────────────────────────────────────────
    wf_translate = {
        "id": "wf_starter_translation",
        "name": "AI 翻译流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_ai_translate",
                "type": "ai",
                "title": "AI 翻译",
                "body": "使用大模型进行智能翻译处理",
                "schemaKey": "schema-translate",
                "configValues": {
                    "targetLanguage": "zh",
                    "prompt": (
                        "你是一位专业翻译。请将以下文档全文翻译为{target_language}。\n"
                        "要求：\n"
                        "1. 保持原文的段落、标题、列表等 Markdown 结构不变；\n"
                        "2. 专业术语首次出现时在括号内附上原文，例如「深度学习（Deep Learning）」；\n"
                        "3. 数字、日期、单位按目标语言习惯格式化；\n"
                        "4. 仅输出译文，禁止添加任何解释或注释。"
                    ),
                },
            },
            _output_node("translated", "md"),
        ],
        "config": {},
    }

    # ── 2. 内容提取 ────────────────────────────────────────────
    wf_summary = {
        "id": "wf_starter_summary",
        "name": "内容提取流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_extract",
                "type": "ai",
                "title": "内容提取",
                "body": "生成摘要和提取关键要点",
                "schemaKey": "schema-extract-summary",
                "configValues": {
                    "extractType": "both",
                    "summaryLength": "medium",
                    "prompt": (
                        "请对以下文档进行内容提取，输出两部分：\n\n"
                        "## 摘要\n"
                        "用 3-5 句话概括文档的核心主题、主要论点和结论。\n\n"
                        "## 关键要点\n"
                        "以编号列表形式列出 5-8 条最重要的信息点，每条不超过 30 字。\n"
                        "优先保留：关键数据、时间节点、行动项和结论性观点。"
                    ),
                },
            },
            _output_node("summary", "md"),
        ],
        "config": {},
    }

    # ── 3. 数据抽取 ────────────────────────────────────────────
    wf_data_extract = {
        "id": "wf_starter_data_extract",
        "name": "数据抽取流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_data_extract",
                "type": "ai",
                "title": "数据抽取",
                "body": "从文档中提取结构化数据",
                "schemaKey": "schema-extract-data",
                "configValues": {
                    "dataFormat": "json",
                    "extractFields": "名称,日期,金额,数量,单位",
                    "prompt": (
                        "请从文档中抽取结构化数据，规则如下：\n"
                        "1. 逐条提取包含以下字段的记录：名称、日期、金额、数量、单位；\n"
                        "2. 日期统一为 YYYY-MM-DD 格式；\n"
                        "3. 金额保留两位小数，带货币符号；\n"
                        "4. 若某字段在原文中不存在，填 null；\n"
                        "5. 仅输出 JSON 数组，不要其他文字。"
                    ),
                },
            },
            _output_node("data", "json"),
        ],
        "config": {},
    }

    # ── 4. 实体提取 ────────────────────────────────────────────
    wf_entity = {
        "id": "wf_starter_entity",
        "name": "实体提取流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_entity",
                "type": "ai",
                "title": "实体提取",
                "body": "按字段与自定义实体类型抽取结构化信息",
                "schemaKey": "schema-entity-extraction",
                "configValues": {
                    "entityFieldList": "姓名\n日期\n金额\n机构名称\n联系方式",
                    "customEntityTypes": "合同条款、项目阶段、关键里程碑",
                    "aliasMap": "买方=甲方; 卖方=乙方; 甲方=委托方",
                    "prompt": (
                        "请从文档中逐段抽取结构化实体，规则：\n"
                        "1. 按「字段列表」提取每个字段对应的值；\n"
                        "2. 同时识别自定义实体类型（合同条款、项目阶段、关键里程碑）；\n"
                        "3. 应用别名映射统一字段名（如「买方」统一为「甲方」）；\n"
                        "4. 日期格式统一为 YYYY-MM-DD；\n"
                        "5. 输出 JSON 对象，结构：{entities: [...], customEntities: [...]}。"
                    ),
                },
            },
            _output_node("entities", "json"),
        ],
        "config": {},
    }

    # ── 5. 内容分析 ────────────────────────────────────────────
    wf_analyze = {
        "id": "wf_starter_analyze",
        "name": "内容分析流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_analyze",
                "type": "ai",
                "title": "内容分析",
                "body": "关键词提取和实体识别",
                "schemaKey": "schema-analyze-content",
                "configValues": {
                    "analysisType": "all",
                    "entityTypes": ["person", "location", "org", "date"],
                    "topK": "10",
                    "prompt": (
                        "请对以下文档进行全面分析，输出三部分：\n\n"
                        "## 关键词\n"
                        "提取 10 个最重要的关键词，按重要性降序排列，格式：`关键词 (权重)`。\n\n"
                        "## 实体识别\n"
                        "识别文档中的命名实体，分类列出：\n"
                        "- 人名：... \n"
                        "- 地名：...\n"
                        "- 机构：...\n"
                        "- 日期：...\n\n"
                        "## 文档主题\n"
                        "用一句话总结文档主题，再用 2-3 句话描述文档涉及的核心话题。"
                    ),
                },
            },
            _output_node("analysis", "md"),
        ],
        "config": {},
    }

    # ── 6. 文本增强 ────────────────────────────────────────────
    wf_enhance = {
        "id": "wf_starter_enhance",
        "name": "文本增强流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_enhance",
                "type": "ai",
                "title": "文本增强",
                "body": "语法检查、润色和改写",
                "schemaKey": "schema-enhance-text",
                "configValues": {
                    "enhanceType": "all",
                    "style": "professional",
                    "prompt": (
                        "请对以下文本进行全面优化，按以下步骤处理：\n\n"
                        "### 1. 语法检查\n"
                        "修正错别字、标点符号错误和语法问题。\n\n"
                        "### 2. 文本润色\n"
                        "提升表达的流畅度和专业性，保持专业风格：\n"
                        "- 消除口语化表达；\n"
                        "- 统一术语和格式；\n"
                        "- 优化长句结构。\n\n"
                        "### 3. 改写\n"
                        "对重点段落进行改写，使逻辑更清晰、层次更分明。\n\n"
                        "请直接输出优化后的完整文本，保留原始 Markdown 结构。"
                    ),
                },
            },
            _output_node("enhanced", "md"),
        ],
        "config": {},
    }

    # ── 7. 敏感信息脱敏 ───────────────────────────────────────
    wf_masking = {
        "id": "wf_starter_masking",
        "name": "敏感信息脱敏流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_masking",
                "type": "ai",
                "title": "敏感信息脱敏",
                "body": "手机号/身份证/邮箱等自动掩码",
                "schemaKey": "schema-sensitive-masking",
                "configValues": {
                    "maskToken": "*",
                    "prompt": (
                        "请对以下文档中的敏感信息进行脱敏处理，规则：\n\n"
                        "**必须脱敏的信息类型：**\n"
                        "1. 手机号码：保留前 3 位和后 4 位，中间用 **** 替换（如 138****1234）；\n"
                        "2. 身份证号：保留前 4 位和后 4 位，中间用 ****** 替换；\n"
                        "3. 邮箱地址：用户名部分保留首字符，其余用 *** 替换（如 z***@example.com）；\n"
                        "4. 银行卡号：仅保留后 4 位，前面全部替换为 ****；\n"
                        "5. 详细地址：保留省/市级，具体街道和门牌号替换为「***」；\n"
                        "6. 人名：保留姓，名替换为「**」（如 张**）。\n\n"
                        "**注意事项：**\n"
                        "- 保持文档原有格式和结构不变；\n"
                        "- 仅替换敏感内容，不要修改其他文本；\n"
                        "- 如果无法确定是否为敏感信息，保持原文不变。"
                    ),
                },
            },
            _output_node("masked", "md"),
        ],
        "config": {},
    }

    # ── 8. 结构化提纲生成 ─────────────────────────────────────
    wf_outline = {
        "id": "wf_starter_outline",
        "name": "提纲生成流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_outline",
                "type": "ai",
                "title": "结构化提纲生成",
                "body": "按层级输出目录提纲",
                "schemaKey": "schema-outline-generate",
                "configValues": {
                    "maxDepth": "3",
                    "prompt": (
                        "请根据文档内容生成结构化提纲，要求：\n\n"
                        "1. 最多 3 级层级（如 1 → 1.1 → 1.1.1）；\n"
                        "2. 每个提纲项不超过 20 字，精准概括该部分核心内容；\n"
                        "3. 同级标题之间保持逻辑并列关系；\n"
                        "4. 标题使用名词短语或动宾结构，避免完整句子；\n"
                        "5. 按文档原有顺序排列，不要跳过任何主要章节。\n\n"
                        "输出格式示例：\n"
                        "```\n"
                        "1. 项目概述\n"
                        "   1.1 背景与目标\n"
                        "   1.2 团队组成\n"
                        "2. 技术方案\n"
                        "   2.1 架构设计\n"
                        "      2.1.1 前端方案\n"
                        "      2.1.2 后端方案\n"
                        "```"
                    ),
                },
            },
            _output_node("outline", "md"),
        ],
        "config": {},
    }

    # ── 9. 文档对比 ─────────────────────────────────────────────
    wf_compare = {
        "id": "wf_starter_compare",
        "name": "文档对比流",
        "icon": "",
        "type": "custom",
        "created_at": ts,
        "updated_at": ts,
        "nodes": [
            _input_node(),
            {
                "id": "n_compare",
                "type": "ai",
                "title": "文档对比",
                "body": "对比两份文档，输出差异报告",
                "schemaKey": "schema-compare-docs",
                "configValues": {
                    "referencePath": "",
                    "compareMode": "detailed",
                    "summaryLevel": "detailed",
                    "prompt": (
                        "请对比以下两份文档并输出差异报告。\n\n"
                        "**文档 A（当前文件）：** {file_a}\n"
                        "**文档 B（参考文件）：** {file_b}\n\n"
                        "--- 文档 A 内容 ---\n{content_a}\n\n"
                        "--- 文档 B 内容 ---\n{content_b}\n\n"
                        "请按以下结构输出对比结果：\n\n"
                        "## 对比概览\n"
                        "简要说明两份文档的基本信息和整体差异概况。\n\n"
                        "## 差异详情\n"
                        "逐项列出所有差异，每条差异包含：\n"
                        "- **差异位置**：涉及的章节/段落\n"
                        "- **文档A内容**：...\n"
                        "- **文档B内容**：...\n"
                        "- **差异类型**：新增 / 删除 / 修改 / 表述差异\n\n"
                        "## 总结\n"
                        "归纳主要差异点，给出核心变化总结。"
                    ),
                },
            },
            _output_node("compared", "md"),
        ],
        "config": {},
    }

    return {
        "wf_starter_translation": wf_translate,
        "wf_starter_summary": wf_summary,
        "wf_starter_data_extract": wf_data_extract,
        "wf_starter_entity": wf_entity,
        "wf_starter_analyze": wf_analyze,
        "wf_starter_enhance": wf_enhance,
        "wf_starter_masking": wf_masking,
        "wf_starter_outline": wf_outline,
        "wf_starter_compare": wf_compare,
    }


def seed_starter_workflows_if_empty(config: Optional[SystemConfig] = None) -> bool:
    """确保所有预设工作流都存在。缺失的会补写，已有的不覆盖。返回是否执行了写入。"""
    from workflow_storage import _load_all, _save_all

    cfg = config or get_config()
    starters = build_starter_workflows()
    all_data = _load_all(cfg)

    changed = False
    for wf_id, wf_def in starters.items():
        if wf_id not in all_data:
            all_data[wf_id] = wf_def
            changed = True

    if changed:
        _save_all(all_data, cfg)
    return changed

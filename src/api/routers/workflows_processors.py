"""
工作流处理器模块 - 各种LLM处理函数
包括翻译、提取、分析、增强、转换、分割等功能
"""
import json
from typing import Any, Dict, List, Optional
from config import SystemConfig
from utils.logger import get_logger

logger = get_logger(__name__)

_LANG_LABEL_MAP = {
    "en": "英语",
    "zh": "中文",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
}


def _target_language_label(config_values: Dict) -> str:
    """将 targetLanguage 配置（code 或中文名）转为提示词用的语言名。"""
    raw = str((config_values or {}).get("targetLanguage") or "中文").strip()
    if raw in _LANG_LABEL_MAP.values():
        return raw
    return _LANG_LABEL_MAP.get(raw, raw or "中文")


def _translate_language_constraints(target_language: str) -> str:
    """按目标语言追加硬性约束，降低本地模型误译为英语的概率。"""
    extra = {
        "日语": "译文必须使用日语（日本語）书写，禁止输出英语或中文。",
        "韩语": "译文必须使用韩语书写，禁止输出英语。",
        "中文": "译文必须使用中文，禁止输出英语。",
        "英语": "译文必须使用英语，禁止输出中文或日语。",
    }
    return extra.get(target_language, f"译文必须使用{target_language}，不要改用其他语言。")


def _get_llm_service():
    """获取 LLM 服务实例。"""
    from core.llm.llm_service import get_llm_service
    service = get_llm_service()
    if not hasattr(service, "is_available") or not service.is_available():
        logger.warning("LLM 服务不可用")
        return None
    return service


def _process_node(content: str, file_name: str, node, config: SystemConfig, state: Dict) -> Optional[str]:
    """根据节点类型分发处理。"""
    node_type = str(getattr(node, "type", "") or "").strip().lower()
    node_title = str(getattr(node, "title", "") or "").strip()
    schema_key = str(getattr(node, "schemaKey", "") or "").strip().lower()
    config_values = node.configValues or {}

    # 优先按 schemaKey 进行稳定分发，避免标题改名导致失配
    if schema_key in {"schema-translate"}:
        return _translate_content(content, file_name, config, config_values)
    if schema_key in {"schema-extract-summary"}:
        return _extract_summary_content(content, file_name, config_values)
    if schema_key in {"schema-extract-data"}:
        return _extract_data_content(content, file_name, config_values)
    if schema_key in {"schema-analyze-content"}:
        return _analyze_content(content, file_name, config_values)
    if schema_key in {"schema-enhance-text"}:
        return _enhance_text_content(content, file_name, config_values)
    if schema_key in {"schema-convert-format"}:
        return _convert_format_content(content, file_name, config_values)
    if schema_key in {"schema-split-document"}:
        return _split_document_content(content, file_name, config_values)
    if schema_key in {"schema-keyword-highlight"}:
        return _keyword_highlight_content(content, file_name, config_values)
    if schema_key in {"schema-sensitive-masking"}:
        return _sensitive_masking_content(content, file_name, config_values)
    if schema_key in {"schema-term-normalize"}:
        return _term_normalize_content(content, file_name, config_values)
    if schema_key in {"schema-outline-generate"}:
        return _outline_generate_content(content, file_name, config_values)
    if schema_key in {"schema-sentiment-enhanced"}:
        return _sentiment_enhanced_content(content, file_name, config_values)
    if schema_key in {"schema-timeline-extract"}:
        return _timeline_extract_content(content, file_name, config_values)
    if schema_key in {"schema-entity-extraction"}:
        return _entity_extraction_content(content, file_name, config_values)
    if schema_key in {"schema-data-process"}:
        return _data_process_content(content, file_name, config_values)
    if schema_key in {"schema-data-clean"}:
        return _data_clean_content(content, file_name, config_values)
    if schema_key in {"schema-table-extract"}:
        return _table_extract_content(content, file_name, config_values)
    if schema_key in {"schema-data-rollup"}:
        return _data_rollup_content(content, file_name, config_values)
    if schema_key in {"schema-save-excel", "schema-save-text"}:
        return content

    # 无 schemaKey 时回退到历史标题匹配逻辑，保持向后兼容
    node_title_lower = node_title.lower()
    if "翻译" in node_title or "translate" in node_title_lower:
        return _translate_content(content, file_name, config, config_values)
    elif "内容提取" in node_title or ("extract" in node_title_lower and "summary" in node_title_lower):
        return _extract_summary_content(content, file_name, config_values)
    elif "数据抽取" in node_title or ("extract" in node_title_lower and "data" in node_title_lower):
        return _extract_data_content(content, file_name, config_values)
    elif "内容分析" in node_title or "分析" in node_title or "analyze" in node_title_lower:
        return _analyze_content(content, file_name, config_values)
    elif "文本增强" in node_title or "增强" in node_title or "enhance" in node_title_lower:
        return _enhance_text_content(content, file_name, config_values)
    elif "格式转换" in node_title or "转换" in node_title or "格式" in node_title or "convert" in node_title_lower:
        return _convert_format_content(content, file_name, config_values)
    elif "文档分割" in node_title or "分割" in node_title or "split" in node_title_lower:
        return _split_document_content(content, file_name, config_values)
    elif "关键词高亮" in node_title or ("keyword" in node_title_lower and "highlight" in node_title_lower):
        return _keyword_highlight_content(content, file_name, config_values)
    elif "脱敏" in node_title or "敏感信息" in node_title or "mask" in node_title_lower:
        return _sensitive_masking_content(content, file_name, config_values)
    elif "术语统一" in node_title or ("term" in node_title_lower and "normalize" in node_title_lower):
        return _term_normalize_content(content, file_name, config_values)
    elif "提纲" in node_title or "outline" in node_title_lower:
        return _outline_generate_content(content, file_name, config_values)
    elif "情感" in node_title or "倾向" in node_title or "sentiment" in node_title_lower:
        return _sentiment_enhanced_content(content, file_name, config_values)
    elif "时间线" in node_title or "timeline" in node_title_lower:
        return _timeline_extract_content(content, file_name, config_values)
    # 处理类型无法识别时，不进行默认翻译，避免误处理
    elif node_type in {"ai", "translate"}:
        logger.warning(f"AI节点未能匹配具体处理类型: type={node_type}, schema={schema_key}, title={node_title}")
        return content
    else:
        logger.warning(f"未知处理类型: type={node_type}, schema={schema_key}, title={node_title}")
        return content


def _text_sample(content: str, limit: int = 8000) -> str:
    return content[:limit] if len(content) > limit else content


def _split_config_text(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    for sep in ["\r\n", "\n", ";", "；", ",", "，"]:
        text = text.replace(sep, "\n")
    return [x.strip() for x in text.split("\n") if x.strip()]


def _chat_or_keep(content: str, prompt: str, task_name: str, temperature: float = 0.3) -> str:
    service = _get_llm_service()
    if not service:
        raise ValueError(f"{task_name}失败：大模型服务不可用，请在设置中配置 API Key 后重试")
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"{task_name}失败: {e}")
        raise ValueError(f"{task_name}失败：{e}") from e


def _entity_extraction_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """按前端配置抽取结构化实体，输出JSON文本。"""
    fields = _split_config_text(config_values.get("entityFieldList"))
    custom_types = _split_config_text(config_values.get("customEntityTypes"))
    alias_map = str(config_values.get("aliasMap") or "").strip()
    custom_prompt = str(config_values.get("prompt") or "").strip()
    if not fields and not custom_types and not custom_prompt:
        raise ValueError("实体提取节点缺少配置：请填写提取字段列表、自定义实体类型或补充抽取规则")

    text = _text_sample(content)
    prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else custom_prompt
    prompt = (
        "请从文档中抽取结构化实体，必须只输出JSON对象，不要输出解释文字。\n"
        "JSON结构：{\"schema\":{\"fields\":[...]},\"entities\":[{...}],\"source_file\":\"...\"}\n"
        f"源文件：{file_name}\n"
        f"字段列表：{fields or '按规则自行判断'}\n"
        f"自定义实体类型：{custom_types or '无'}\n"
        f"字段别名映射：{alias_map or '无'}\n"
        f"补充规则：{prompt or '无'}\n\n"
        f"文档内容：\n{text}"
    )
    return _chat_or_keep(content, prompt, "实体提取", temperature=0.2)


def _data_process_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """按配置对表格/结构化文本做排序、筛选、汇总等处理。"""
    process_kind = str(config_values.get("processKind") or "").strip()
    allowed = {"sort", "filter", "aggregate", "dedupe", "fill_null", "computed_column", "merge_columns", "split_column"}
    if process_kind not in allowed:
        raise ValueError("数据处理节点配置无效：processKind必须是排序、筛选、汇总、去重、填充空值、新增计算列、合并列或拆分列")

    required_by_kind = {
        "sort": ["sortColumn"],
        "filter": ["filterExpr"],
        "aggregate": ["aggregateColumn", "aggregateOp"],
        "fill_null": ["fillColumns"],
        "computed_column": ["computedColumnName", "computedFormula"],
        "merge_columns": ["mergeSourceColumns", "mergeTargetColumn"],
        "split_column": ["splitSourceColumn", "splitIntoColumns"],
    }
    missing = [key for key in required_by_kind.get(process_kind, []) if not str(config_values.get(key) or "").strip()]
    if missing:
        raise ValueError(f"数据处理节点缺少配置：{', '.join(missing)}")

    text = _text_sample(content)
    prompt = (
        "请按配置处理下方表格或结构化文本。优先保持输入的数据格式；如果无法保留原格式，输出Markdown表格。\n"
        "不要编造不存在的列或数据；配置无法完全执行时，在结果末尾用【处理说明】写明原因。\n"
        f"处理类型：{process_kind}\n"
        f"配置JSON：{json.dumps(config_values, ensure_ascii=False)}\n\n"
        f"内容：\n{text}"
    )
    return _chat_or_keep(content, prompt, "数据处理", temperature=0.2)


def _data_clean_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """按清洗规则规范化结构化文本。"""
    rules = config_values.get("cleanRules") or []
    if isinstance(rules, str):
        rules = _split_config_text(rules)
    if not isinstance(rules, list) or not rules:
        raise ValueError("数据清洗节点缺少配置：cleanRules不能为空")

    result = content
    if "trim_spaces" in rules:
        result = "\n".join(line.strip() for line in result.splitlines())

    complex_rules = [r for r in rules if r != "trim_spaces"]
    custom_prompt = str(config_values.get("prompt") or "").strip()
    if not complex_rules and not custom_prompt:
        return result

    text = _text_sample(result)
    prompt = (
        "请按配置清洗下方数据，保持原数据格式和列结构，无法处理的规则在结果末尾用【清洗说明】说明。\n"
        f"清洗规则：{complex_rules or rules}\n"
        f"目标日期格式：{config_values.get('dateFormatPattern') or '不指定'}\n"
        f"数字小数位数：{config_values.get('numberDecimalPlaces') or '不指定'}\n"
        f"补充规则：{custom_prompt or '无'}\n\n"
        f"内容：\n{text}"
    )
    return _chat_or_keep(result, prompt, "数据清洗", temperature=0.2)


def _table_extract_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """从文档文本中抽取表格，输出Markdown表格或表格清单。"""
    strategy = str(config_values.get("tableStrategy") or "first").strip()
    if strategy not in {"first", "all", "by_index"}:
        raise ValueError("表格提取节点配置无效：tableStrategy必须为first、all或by_index")
    if strategy == "by_index":
        try:
            table_index = int(config_values.get("tableIndex"))
            if table_index <= 0:
                raise ValueError()
        except Exception:
            raise ValueError("表格提取节点缺少配置：tableIndex必须是从1开始的正整数")

    text = _text_sample(content)
    prompt = (
        "请从文档中提取表格，输出Markdown表格；如果有多个表格，请用二级标题区分。\n"
        "不要输出表格以外的解释，确实没有表格时输出：未发现可提取表格。\n"
        f"提取策略：{strategy}\n"
        f"表格序号：{config_values.get('tableIndex') or '不指定'}\n"
        f"首行为表头：{bool(config_values.get('hasHeader', True))}\n"
        f"补充说明：{config_values.get('prompt') or '无'}\n\n"
        f"文档内容：\n{text}"
    )
    return _chat_or_keep(content, prompt, "表格提取", temperature=0.2)


def _data_rollup_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """按维度与指标对结构化数据做汇总。"""
    dims = _split_config_text(config_values.get("rollupDims"))
    metrics = _split_config_text(config_values.get("rollupMetrics"))
    custom_prompt = str(config_values.get("prompt") or "").strip()
    if not dims and not metrics and not custom_prompt:
        raise ValueError("数据汇总节点缺少配置：请填写分类维度、指标与聚合或补充说明")

    text = _text_sample(content)
    prompt = (
        "请对下方数据做统计汇总，并输出Markdown表格和简要结论。\n"
        "如果数据不足以汇总，请说明缺失的列或条件，不要编造数据。\n"
        f"分类维度：{dims or '无'}\n"
        f"指标与聚合：{metrics or '无'}\n"
        f"补充说明：{custom_prompt or '无'}\n\n"
        f"内容：\n{text}"
    )
    return _chat_or_keep(content, prompt, "数据汇总", temperature=0.2)


def _translate_content(content: str, file_name: str, config: SystemConfig, config_values: Dict = None) -> Optional[str]:
    """使用 LLM 翻译文档内容。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("文档翻译失败：大模型服务不可用，请在设置中配置 API Key 后重试")

    config_values = config_values or {}
    text = content[:8000] if len(content) > 8000 else content
    target_language = _target_language_label(config_values)

    custom_prompt = str(config_values.get("prompt") or "").strip()
    if custom_prompt:
        prompt = (
            custom_prompt.replace("{content}", text)
            .replace("{target_language}", target_language)
            .replace("{targetLanguage}", target_language)
        )
        if "{content}" not in custom_prompt:
            prompt = (
                f"{prompt}\n\n"
                f"【硬性要求】目标语言：{target_language}。"
                f"必须将下方全文翻译为{target_language}，仅输出译文，不要保留未翻译的原文段落。\n\n"
                f"文档内容：\n{text}"
            )
    else:
        prompt = (
            f"你是一个专业的文档翻译助手。请将以下文档全文翻译为{target_language}，保持原文的格式和结构。\n"
            "注意：\n"
            "1. 保持段落结构不变\n"
            "2. 保留标题层级\n"
            "3. 保留代码块、表格等特殊格式\n"
            "4. 不要添加或删除内容，只进行翻译\n"
            "5. 仅输出译文，不要附带解释\n"
            f"6. {_translate_language_constraints(target_language)}\n\n"
            f"文档内容：\n{text}"
        )

    lang_constraint = _translate_language_constraints(target_language)
    if lang_constraint not in prompt:
        prompt = f"{prompt}\n\n【语言约束】{lang_constraint}"

    try:
        response = service.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"你是文档翻译器。用户指定的目标语言是：{target_language}。"
                        f"{lang_constraint} 只输出译文正文。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"LLM 翻译失败: {e}")
        raise ValueError(f"文档翻译失败：{e}") from e


def _extract_summary_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """提取文档摘要和要点。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("内容提取失败：大模型服务不可用，请在设置中配置 API Key 后重试")
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        extract_type = config_values.get("extractType", "summary")
        summary_length = config_values.get("summaryLength", "medium")
        length_hint = {"short": "200字以内", "medium": "500字以内", "detailed": "1000字以内"}.get(summary_length, "500字以内")
        
        text = content[:8000] if len(content) > 8000 else content
        
        if extract_type == "summary":
            prompt = f"请为以下文档生成摘要（{length_hint}）：\n{text}"
        elif extract_type == "keypoints":
            prompt = f"请从以下文档中提取3-5个关键要点，用\n开头列出：\n{text}"
        else:  # both
            prompt = f"请为以下文档生成摘要（{length_hint}），然后在【要点】下列出3-5个关键要点：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"摘要提取失败: {e}")
        raise ValueError(f"内容提取失败：{e}") from e


def _extract_data_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """从文档中提取结构化数据。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        data_format = config_values.get("dataFormat", "json")
        extract_fields = config_values.get("extractFields", "")
        text = content[:8000] if len(content) > 8000 else content
        
        prompt = f"请从以下文档中提取数据，格式为{data_format}\n"
        if extract_fields:
            prompt += f"需要提取的字段：{extract_fields}\n"
        prompt += f"文档内容：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        raise ValueError(f"数据提取失败：{e}") from e


def _analyze_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """分析文档内容（关键词、实体、情感等）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    def _normalize_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [x.strip() for x in v.split(',') if x.strip()]
        return []

    def _to_int(v, default):
        try:
            n = int(v)
            return n if n > 0 else default
        except Exception:
            return default
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    analysis_type = config_values.get("analysisType", "keywords")
    entity_types = _normalize_list(config_values.get("entityTypes", []))
    entity_map = {
        "person": "人名",
        "location": "地名",
        "org": "机构",
        "date": "日期",
    }
    selected_entity_labels = [entity_map.get(x, x) for x in entity_types] if entity_types else ["人名", "地名", "机构", "日期"]
    selected_entity_desc = "、".join(selected_entity_labels)

    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
        if analysis_type == "entities":
            prompt += (
                "\n\n附加硬约束（必须遵守）：\n"
                f"- 只允许抽取这些实体类型：{selected_entity_desc}\n"
                "- 严禁输出未在允许列表中的任何实体类型\n"
                "- 若无命中，返回空数组\n"
            )
    else:
        top_k = _to_int(config_values.get("topK", 10), 10)
        text = content[:8000] if len(content) > 8000 else content
        
        if analysis_type == "keywords":
            prompt = f"请提取以下文档的{top_k}个关键词，仅输出关键词列表（逗号分隔，不要解释）：\n{text}"
        elif analysis_type == "entities":
            prompt = (
                "请执行实体抽取，并严格遵循以下规则：\n"
                f"1. 只允许抽取这些实体类型：{selected_entity_desc}\n"
                "2. 严禁输出未在允许列表中的任何实体类型\n"
                "3. 若某一允许类型没有命中，返回空数组\n"
                "4. 输出必须是 JSON 对象，不要附加解释文字\n"
                f"5. JSON 的键只能来自：{selected_entity_desc}\n"
                f"文档内容：\n{text}"
            )
        else:  # all
            prompt = (
                "请对以下文档进行全面分析，输出结构为：关键词、实体、主题、情感。\n"
                f"其中关键词数量为 {top_k} 个；实体部分只允许这些类型：{selected_entity_desc}。\n"
                "实体部分若无命中可返回空数组，不要新增其他实体类型。\n"
                f"文档内容：\n{text}"
            )
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"内容分析失败: {e}")
        raise ValueError(f"内容分析失败：{e}") from e


def _enhance_text_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """文本增强：语法检查、润色、改写等。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        enhance_type = config_values.get("enhanceType", "grammar")
        style = config_values.get("style", "concise")
        text = content[:8000] if len(content) > 8000 else content
        
        style_desc = {
            "concise": "简洁风格",
            "formal": "学术风格",
            "casual": "口语风格",
            "professional": "专业风格"
        }.get(style, "简洁风格")
        
        if enhance_type == "grammar":
            prompt = f"请检查并修正以下文本的语法错误，只返回修正后的文本：\n{text}"
        elif enhance_type == "polish":
            prompt = f"请润色以下文本为{style_desc}，提高表达质量，保持原意：\n{text}"
        elif enhance_type == "rephrase":
            prompt = f"请改写以下文本为{style_desc}，保持原意但使用不同的措辞：\n{text}"
        else:  # all
            prompt = f"请对以下文本进行全面优化：1. 检查语法 2. 润色表达 3. 调整为{style_desc}。返回优化后的文本：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"文本增强失败: {e}")
        raise ValueError(f"文本增强失败：{e}") from e


def _convert_format_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """格式转换。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        target_format = config_values.get("targetFormat", "markdown")
        preserve_formatting = bool(config_values.get("preserveFormatting", False))
        preserve_structure = config_values.get("preserveStructure", True)
        text = content[:8000] if len(content) > 8000 else content
        
        format_names = {"markdown": "Markdown", "html": "HTML", "plaintext": "纯文本", "json": "JSON"}
        target_name = format_names.get(target_format, target_format)
        
        prompt = f"请将以下文本转换为{target_name}格式"
        if preserve_formatting:
            prompt += "，尽可能保留原有格式细节（如强调、层次与标记）"
        if preserve_structure:
            prompt += "，保持原有的结构和层级"
        prompt += f"：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"格式转换失败: {e}")
        raise ValueError(f"格式转换失败：{e}") from e


def _split_document_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """文档分割（按章节、段落或大小）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", content[:8000]) if "{content}" in custom_prompt else f"{custom_prompt}\n{content[:8000]}"
    else:
        split_method = config_values.get("splitMethod", "paragraph")
        split_size = str(config_values.get("splitSize", "") or "").strip()
        preserve_context = bool(config_values.get("preserveContext", False))
        context_tip = "，并在相邻片段间保留必要上下文重叠" if preserve_context else ""
        
        if split_method == "section":
            prompt = f"请按章节/段落分割以下文档，为每个部分添加标题标记（# 或 ##）{context_tip}。保留原文内容：\n{content[:8000]}"
        elif split_method == "paragraph":
            prompt = f"请将以下文档按段落分割，每段加上序号{context_tip}，保留原文内容：\n{content[:8000]}"
        elif split_method == "size":
            size_desc = split_size or "500字"
            prompt = f"请将以下文档分成多个部分，每个部分约{size_desc}，用【分割】标记分割点{context_tip}，保留原文：\n{content[:8000]}"
        else:  # page
            page_desc = split_size or "一页"
            prompt = f"请将以下文档按逻辑页面分割（每段约{page_desc}）{context_tip}，用【新页面】标记，保留原文：\n{content[:8000]}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"文档分割失败: {e}")
        raise ValueError(f"文档分割失败：{e}") from e


def _keyword_highlight_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """提取关键词并在文本中标注。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    top_k = config_values.get("topK", 10)
    marker = str(config_values.get("marker", "**")).strip() or "**"
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请完成“关键词高亮输出”任务：\n"
            f"1) 从文本中提取不超过 {top_k} 个关键词；\n"
            f"2) 在原文中用 {marker}关键词{marker} 方式标注；\n"
            "3) 输出格式：\n"
            "【关键词】\n"
            "- 关键词1\n"
            "- 关键词2\n"
            "...\n"
            "【高亮结果】\n"
            "<带标注文本>\n"
            "仅输出以上结构。\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"关键词高亮失败: {e}")
        raise ValueError(f"关键词高亮失败：{e}") from e


def _sensitive_masking_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """敏感信息脱敏。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    mask_token = str(config_values.get("maskToken", "*")).strip() or "*"
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请对文本进行敏感信息脱敏，至少处理以下类型：手机号、身份证号、邮箱、银行卡号。\n"
            f"脱敏符号使用：{mask_token}\n"
            "规则：\n"
            "- 手机号保留前3后4\n"
            "- 身份证保留前6后4\n"
            "- 邮箱保留首字符与域名\n"
            "- 其他长数字串按前后各2位保留\n"
            "输出：仅返回脱敏后的文本。\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.2, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"敏感信息脱敏失败: {e}")
        raise ValueError(f"敏感信息脱敏失败：{e}") from e


def _term_normalize_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """按术语词典进行统一替换。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    term_dict = str(config_values.get("termDictionary", "")).strip()
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请根据术语词典统一文本表达，未命中词典时保持原文。\n"
            "术语词典格式示例：A=>标准术语A; B=>标准术语B\n"
            f"词典：{term_dict or '（未提供词典，请先提取并建议统一术语）'}\n"
            "输出格式：\n"
            "【术语映射】\n"
            "- 原词 => 新词\n"
            "【规范化文本】\n"
            "<替换后文本>\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.2, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"术语统一失败: {e}")
        raise ValueError(f"术语统一失败：{e}") from e


def _outline_generate_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """结构化提纲生成。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    max_depth = config_values.get("maxDepth", 3)
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请基于文本生成结构化提纲，按层级输出目录。\n"
            f"层级深度不超过 {max_depth} 级，使用 Markdown 标题或有序编号均可。\n"
            "要求：覆盖主要章节、逻辑完整、层级清晰。\n"
            "仅输出提纲。\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"提纲生成失败: {e}")
        raise ValueError(f"提纲生成失败：{e}") from e


def _sentiment_enhanced_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """情感/倾向分析增强（标签+打分）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请对文本做情感/倾向分析，并输出可读结果。\n"
            "要求：\n"
            "- 给出总体标签（正向/中性/负向）\n"
            "- 给出 0-100 分倾向分值（越高越正向）\n"
            "- 给出 3-5 条依据句\n"
            "输出格式：\n"
            "【总体标签】\n"
            "【倾向得分】\n"
            "【分析依据】\n"
            "【简要结论】\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"情感分析增强失败: {e}")
        raise ValueError(f"情感分析失败：{e}") from e


def _timeline_extract_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """时间线抽取（事件+时间排序）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    text = content[:8000] if len(content) > 8000 else content
    custom_prompt = str(config_values.get("prompt", "")).strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        prompt = (
            "请从文本中抽取时间线事件，并按时间升序排序。\n"
            "要求：\n"
            "- 提取时间（精确到日期或时间段）\n"
            "- 提取对应事件描述\n"
            "- 无明确时间的事件放在“未明确时间”分组\n"
            "输出格式：\n"
            "【时间线】\n"
            "1. YYYY-MM-DD - 事件...\n"
            "2. ...\n"
            "【未明确时间】\n"
            "- 事件...\n\n"
            f"文本：\n{text}"
        )
    try:
        response = service.chat(messages=[{"role": "user", "content": prompt}], temperature=0.2, strip_markdown_output=False)
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"时间线抽取失败: {e}")
        raise ValueError(f"时间线抽取失败：{e}") from e

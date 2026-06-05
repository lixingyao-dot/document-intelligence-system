"""
工作流处理器模块 - 组件库中保留节点的 LLM 处理函数。
"""
from typing import Any, Dict, List, Optional
from config import SystemConfig
from utils.file_utils import split_text_semantic_with_offset
from utils.logger import get_logger

logger = get_logger(__name__)

# 单次送入模型的正文字符上限（按句号/换行语义分块，长文档逐段处理后拼接）
_LLM_CHUNK_CHARS = 4500
_TRANSLATE_CHUNK_CHARS = _LLM_CHUNK_CHARS

# 已从组件库下架（旧工作流命中时原样透传，避免执行失败）
_RETIRED_SCHEMA_KEYS = frozenset({
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
})

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

    if schema_key in _RETIRED_SCHEMA_KEYS:
        logger.warning("工作流组件已下架，跳过处理: schema=%s title=%s", schema_key, node_title)
        return content

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
    if schema_key in {"schema-sensitive-masking"}:
        return _sensitive_masking_content(content, file_name, config_values)
    if schema_key in {"schema-outline-generate"}:
        return _outline_generate_content(content, file_name, config_values)
    if schema_key in {"schema-entity-extraction"}:
        return _entity_extraction_content(content, file_name, config_values)
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
    elif "脱敏" in node_title or "敏感信息" in node_title or "mask" in node_title_lower:
        return _sensitive_masking_content(content, file_name, config_values)
    elif "提纲" in node_title or "outline" in node_title_lower:
        return _outline_generate_content(content, file_name, config_values)
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


def _split_text_for_llm(content: str, max_chars: int = _LLM_CHUNK_CHARS) -> List[str]:
    """长文档按语义边界分块，避免硬截断只处理开头一段。"""
    text = content or ""
    if len(text) <= max_chars:
        return [text]
    chunks = [piece for piece, _ in split_text_semantic_with_offset(text, max_chars)]
    return chunks if chunks else [text[:max_chars]]


def _split_text_for_translation(content: str, max_chars: int = _TRANSLATE_CHUNK_CHARS) -> List[str]:
    return _split_text_for_llm(content, max_chars)


def _chunk_processing_hint(chunk_index: int, chunk_total: int, instruction: str) -> str:
    if chunk_total <= 1:
        return ""
    return (
        f"\n\n【分段说明】这是长文档的第 {chunk_index}/{chunk_total} 段。"
        f"{instruction}"
    )


def _output_token_budget(text_len: int, *, min_tokens: int = 4096, max_cap: int = 16384) -> int:
    return max(min_tokens, min(max_cap, text_len * 2 + 1024))


def _llm_chat(
    service,
    messages: List[Dict[str, str]],
    text_len: int,
    *,
    temperature: float = 0.3,
) -> str:
    response = service.chat(
        messages=messages,
        temperature=temperature,
        max_tokens=_output_token_budget(text_len),
        strip_markdown_output=False,
    )
    return response if isinstance(response, str) else str(response)


def _map_document_chunks(
    content: str,
    file_name: str,
    task_label: str,
    process_piece,
) -> str:
    """对长文档分块 map，再拼接为完整结果（用于翻译/增强/脱敏等全文变换）。"""
    chunks = _split_text_for_llm(content)
    total = len(chunks)
    if total > 1:
        logger.info(
            "工作流%s分块: file=%s total_chars=%d chunks=%d",
            task_label,
            file_name,
            len(content or ""),
            total,
        )
    parts: List[str] = []
    for idx, piece in enumerate(chunks, start=1):
        if not piece.strip():
            parts.append(piece)
            continue
        out = process_piece(piece, idx, total)
        parts.append(out)
        if total > 1:
            logger.info(
                "工作流%s进度: file=%s chunk=%d/%d in=%d out=%d",
                task_label,
                file_name,
                idx,
                total,
                len(piece),
                len(out),
            )
    return "".join(parts)


def _build_translate_prompt(
    text: str,
    target_language: str,
    config_values: Dict,
    *,
    chunk_index: int = 1,
    chunk_total: int = 1,
) -> str:
    """构造翻译 user prompt（支持长文档分块提示）。"""
    custom_prompt = str(config_values.get("prompt") or "").strip()
    chunk_hint = ""
    if chunk_total > 1:
        chunk_hint = (
            f"\n\n【分段说明】这是长文档的第 {chunk_index}/{chunk_total} 段。"
            "请完整翻译本段全部内容，仅输出本段译文，不要省略或概括。"
        )

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
                f"必须将下方全文翻译为{target_language}，仅输出译文，不要保留未翻译的原文段落。"
                f"{chunk_hint}\n\n"
                f"文档内容：\n{text}"
            )
        else:
            prompt = f"{prompt}{chunk_hint}"
    else:
        prompt = (
            f"你是一个专业的文档翻译助手。请将以下文档全文翻译为{target_language}，保持原文的格式和结构。\n"
            "注意：\n"
            "1. 保持段落结构不变\n"
            "2. 保留标题层级\n"
            "3. 保留代码块、表格等特殊格式\n"
            "4. 不要添加或删除内容，只进行翻译\n"
            "5. 仅输出译文，不要附带解释\n"
            f"6. {_translate_language_constraints(target_language)}\n"
            f"{chunk_hint}\n\n"
            f"文档内容：\n{text}"
        )

    lang_constraint = _translate_language_constraints(target_language)
    if lang_constraint not in prompt:
        prompt = f"{prompt}\n\n【语言约束】{lang_constraint}"
    return prompt


def _translate_single_chunk(
    service,
    text: str,
    target_language: str,
    config_values: Dict,
    *,
    chunk_index: int = 1,
    chunk_total: int = 1,
) -> str:
    """翻译单个文本块。"""
    lang_constraint = _translate_language_constraints(target_language)
    prompt = _build_translate_prompt(
        text,
        target_language,
        config_values,
        chunk_index=chunk_index,
        chunk_total=chunk_total,
    )
    # 译文长度通常接近原文，默认 max_tokens=4096 容易截断输出
    out_budget = max(4096, min(16384, len(text) * 2 + 1024))
    response = service.chat(
        messages=[
            {
                "role": "system",
                "content": (
                    f"你是文档翻译器。用户指定的目标语言是：{target_language}。"
                    f"{lang_constraint} 只输出译文正文，不要省略段落。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=out_budget,
        strip_markdown_output=False,
    )
    return response if isinstance(response, str) else str(response)


def _translate_content(content: str, file_name: str, config: SystemConfig, config_values: Dict = None) -> Optional[str]:
    """使用 LLM 翻译文档内容（长文档自动分块，逐段翻译后拼接）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("文档翻译失败：大模型服务不可用，请在设置中配置 API Key 后重试")

    config_values = config_values or {}
    target_language = _target_language_label(config_values)

    def _process(piece: str, chunk_index: int, chunk_total: int) -> str:
        return _translate_single_chunk(
            service,
            piece,
            target_language,
            config_values,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )

    try:
        return _map_document_chunks(content, file_name, "翻译", _process)
    except Exception as e:
        logger.error(f"LLM 翻译失败: {e}")
        raise ValueError(f"文档翻译失败：{e}") from e


def _summary_length_hint(config_values: Dict) -> str:
    summary_length = config_values.get("summaryLength", "medium")
    return {"short": "200字以内", "medium": "500字以内", "detailed": "1000字以内"}.get(
        summary_length, "500字以内"
    )


def _build_summary_chunk_prompt(
    text: str,
    config_values: Dict,
    *,
    chunk_index: int = 1,
    chunk_total: int = 1,
    partial: bool = False,
) -> str:
    """构造摘要 prompt；partial=True 时对单段做局部摘要/要点。"""
    custom_prompt = str(config_values.get("prompt") or "").strip()
    extract_type = config_values.get("extractType", "summary")
    length_hint = _summary_length_hint(config_values)
    chunk_hint = _chunk_processing_hint(
        chunk_index,
        chunk_total,
        "请仅基于本段内容生成摘要/要点，不要编造本段未出现的信息。"
        if partial
        else "",
    )

    if custom_prompt:
        prompt = (
            custom_prompt.replace("{content}", text)
            if "{content}" in custom_prompt
            else f"{custom_prompt}\n{text}"
        )
        return f"{prompt}{chunk_hint}"

    if partial:
        if extract_type == "summary":
            return (
                f"请为以下文档片段生成简短摘要（每段不超过 {length_hint}）：\n"
                f"{chunk_hint}\n\n{text}"
            )
        if extract_type == "keypoints":
            return (
                "请从以下文档片段中提取 2-4 个关键要点，用换行列出：\n"
                f"{chunk_hint}\n\n{text}"
            )
        return (
            f"请为以下文档片段生成简短摘要，并列出 2-4 个要点：\n"
            f"{chunk_hint}\n\n{text}"
        )

    if extract_type == "summary":
        return f"请为以下文档生成摘要（{length_hint}）：\n{text}"
    if extract_type == "keypoints":
        return f"请从以下文档中提取3-5个关键要点，用\n开头列出：\n{text}"
    return (
        f"请为以下文档生成摘要（{length_hint}），然后在【要点】下列出3-5个关键要点：\n{text}"
    )


def _build_summary_merge_prompt(partial_summaries: List[str], config_values: Dict) -> str:
    extract_type = config_values.get("extractType", "summary")
    length_hint = _summary_length_hint(config_values)
    joined = "\n\n---\n\n".join(
        f"【片段 {i}】\n{s.strip()}" for i, s in enumerate(partial_summaries, start=1) if s.strip()
    )
    if extract_type == "summary":
        return (
            f"以下是同一长文档各片段的局部摘要。请合并为一份连贯的全文摘要（{length_hint}），"
            "去重、理顺逻辑，仅输出最终摘要：\n\n"
            f"{joined}"
        )
    if extract_type == "keypoints":
        return (
            "以下是同一长文档各片段提取的要点。请合并去重，输出 3-8 条全文关键要点，"
            "每条一行，以 - 开头：\n\n"
            f"{joined}"
        )
    return (
        f"以下是同一长文档各片段的局部摘要与要点。请合并为一份全文结果："
        f"先给出摘要（{length_hint}），再在【要点】下给出 3-8 条合并后的关键要点：\n\n"
        f"{joined}"
    )


def _extract_summary_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """提取文档摘要和要点（长文档：分块摘要 → 总摘要）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("内容提取失败：大模型服务不可用，请在设置中配置 API Key 后重试")

    config_values = config_values or {}
    chunks = _split_text_for_llm(content)
    total = len(chunks)

    try:
        if total == 1:
            piece = chunks[0]
            prompt = _build_summary_chunk_prompt(piece, config_values)
            return _llm_chat(
                service,
                [{"role": "user", "content": prompt}],
                len(piece),
                temperature=0.5,
            )

        logger.info(
            "工作流摘要分块: file=%s total_chars=%d chunks=%d",
            file_name,
            len(content or ""),
            total,
        )
        partials: List[str] = []
        for idx, piece in enumerate(chunks, start=1):
            if not piece.strip():
                continue
            prompt = _build_summary_chunk_prompt(
                piece, config_values, chunk_index=idx, chunk_total=total, partial=True
            )
            partial = _llm_chat(
                service,
                [{"role": "user", "content": prompt}],
                len(piece),
                temperature=0.5,
            )
            partials.append(partial)
            logger.info("工作流摘要片段: file=%s chunk=%d/%d", file_name, idx, total)

        merge_prompt = _build_summary_merge_prompt(partials, config_values)
        return _llm_chat(
            service,
            [{"role": "user", "content": merge_prompt}],
            len(merge_prompt),
            temperature=0.4,
        )
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


def _build_enhance_prompt(text: str, config_values: Dict, *, chunk_index: int = 1, chunk_total: int = 1) -> str:
    custom_prompt = str(config_values.get("prompt") or "").strip()
    chunk_hint = _chunk_processing_hint(
        chunk_index,
        chunk_total,
        "请完整处理本段全部文本，仅输出处理后的本段正文，不要省略或概括。",
    )
    if custom_prompt:
        prompt = (
            custom_prompt.replace("{content}", text)
            if "{content}" in custom_prompt
            else f"{custom_prompt}\n{text}"
        )
        return f"{prompt}{chunk_hint}"

    enhance_type = config_values.get("enhanceType", "grammar")
    style = config_values.get("style", "concise")
    style_desc = {
        "concise": "简洁风格",
        "formal": "学术风格",
        "casual": "口语风格",
        "professional": "专业风格",
    }.get(style, "简洁风格")

    if enhance_type == "grammar":
        base = f"请检查并修正以下文本的语法错误，只返回修正后的文本：\n{text}"
    elif enhance_type == "polish":
        base = f"请润色以下文本为{style_desc}，提高表达质量，保持原意：\n{text}"
    elif enhance_type == "rephrase":
        base = f"请改写以下文本为{style_desc}，保持原意但使用不同的措辞：\n{text}"
    else:
        base = (
            f"请对以下文本进行全面优化：1. 检查语法 2. 润色表达 3. 调整为{style_desc}。"
            f"返回优化后的文本：\n{text}"
        )
    return f"{base}{chunk_hint}"


def _enhance_text_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """文本增强：语法检查、润色、改写等（长文档分块处理后拼接）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    config_values = config_values or {}

    def _process(piece: str, chunk_index: int, chunk_total: int) -> str:
        prompt = _build_enhance_prompt(
            piece, config_values, chunk_index=chunk_index, chunk_total=chunk_total
        )
        return _llm_chat(
            service,
            [{"role": "user", "content": prompt}],
            len(piece),
            temperature=0.6,
        )

    try:
        return _map_document_chunks(content, file_name, "文本增强", _process)
    except Exception as e:
        logger.error(f"文本增强失败: {e}")
        raise ValueError(f"文本增强失败：{e}") from e


def _build_masking_prompt(text: str, config_values: Dict, *, chunk_index: int = 1, chunk_total: int = 1) -> str:
    mask_token = str(config_values.get("maskToken", "*")).strip() or "*"
    custom_prompt = str(config_values.get("prompt") or "").strip()
    chunk_hint = _chunk_processing_hint(
        chunk_index,
        chunk_total,
        "请对本段全部文本做脱敏，仅输出脱敏后的本段正文，不要省略段落。",
    )
    if custom_prompt:
        prompt = (
            custom_prompt.replace("{content}", text)
            if "{content}" in custom_prompt
            else f"{custom_prompt}\n{text}"
        )
        return f"{prompt}{chunk_hint}"

    return (
        "请对文本进行敏感信息脱敏，至少处理以下类型：手机号、身份证号、邮箱、银行卡号。\n"
        f"脱敏符号使用：{mask_token}\n"
        "规则：\n"
        "- 手机号保留前3后4\n"
        "- 身份证保留前6后4\n"
        "- 邮箱保留首字符与域名\n"
        "- 其他长数字串按前后各2位保留\n"
        "输出：仅返回脱敏后的文本。\n"
        f"{chunk_hint}\n\n"
        f"文本：\n{text}"
    )


def _sensitive_masking_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """敏感信息脱敏（长文档分块脱敏后拼接）。"""
    service = _get_llm_service()
    if not service:
        raise ValueError("大模型服务不可用，请在设置中配置 API Key 后重试")

    config_values = config_values or {}

    def _process(piece: str, chunk_index: int, chunk_total: int) -> str:
        prompt = _build_masking_prompt(
            piece, config_values, chunk_index=chunk_index, chunk_total=chunk_total
        )
        return _llm_chat(
            service,
            [{"role": "user", "content": prompt}],
            len(piece),
            temperature=0.2,
        )

    try:
        return _map_document_chunks(content, file_name, "脱敏", _process)
    except Exception as e:
        logger.error(f"敏感信息脱敏失败: {e}")
        raise ValueError(f"敏感信息脱敏失败：{e}") from e


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

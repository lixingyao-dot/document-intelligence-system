"""
Agent_B: 实体提取Agent
负责从非结构化文档中提取数据为JSON格式
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from utils.file_utils import read_excel_template_columns, split_text_semantic_with_offset
from utils.logger import get_logger
from .base_agent import BaseAgent, AgentResponse
from config import SystemConfig, get_config
from core.orchestrator.task_spec import TaskSpec


def _normalize_label(text: str) -> str:
    """归一化字段名：去单位括号、空白与常见标点，便于别名匹配。"""
    s = str(text or "").strip().lower()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = re.sub(r"[\s_\-·、，,。.;；:：]", "", s)
    return s


def _column_aliases(column: str) -> List[str]:
    aliases = [column]
    without_unit = re.sub(r"[（(][^）)]*[）)]", "", column).strip()
    if without_unit and without_unit != column:
        aliases.append(without_unit)
    norm = _normalize_label(column)
    if "城市" in column or norm in ("城市名", "城市名称", "地名"):
        aliases.extend(["城市", "城市名", "城市名称", "地名", "名称"])
    if "gdp" in norm and "人均" not in column:
        aliases.extend(["GDP总量", "国内生产总值", "地区生产总值"])
    if "人均" in column and "gdp" in norm:
        aliases.extend(["人均GDP", "人均生产总值"])
    if "人口" in column:
        aliases.extend(["常住人口", "人口", "常驻人口"])
    if "预算收入" in column or "财政收入" in column:
        aliases.extend(["一般公共预算收入", "预算收入", "财政收入", "公共预算收入"])
    if "人均" in column:
        aliases.extend(["人均GDP", "人均生产总值"])
    dedup: List[str] = []
    seen = set()
    for item in aliases:
        if item and item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def _build_alias_to_column(template_columns: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in template_columns:
        for alias in _column_aliases(col):
            mapping[_normalize_label(alias)] = col
        mapping[_normalize_label(col)] = col
    return mapping


def _resolve_field_name(raw_key: str, template_columns: List[str], alias_map: Dict[str, str]) -> Optional[str]:
    norm = _normalize_label(raw_key)
    if norm in alias_map:
        return alias_map[norm]
    for col in template_columns:
        if _normalize_label(col) == norm:
            return col
    return None


def _guess_key_column(template_columns: List[str]) -> str:
    for col in template_columns:
        if any(token in col for token in ("城市", "名称", "名字", "主体", "单位")):
            return col
    return template_columns[0] if template_columns else ""


def _extract_labeled_records(text: str, template_columns: List[str]) -> List[Dict[str, str]]:
    """规则抽取：适配「城市名 + 字段：数值」类半结构化 Word 段落。"""
    if not text.strip() or not template_columns:
        return []

    key_col = _guess_key_column(template_columns)
    alias_map = _build_alias_to_column(template_columns)
    records: List[Dict[str, str]] = []
    blocks = re.split(r"\n\s*\n+", text)

    for block in blocks:
        block = block.strip()
        if len(block) < 4:
            continue

        row: Dict[str, str] = {}
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]

        if lines and "：" not in lines[0] and ":" not in lines[0] and len(lines[0]) <= 12:
            if re.match(r"^[\u4e00-\u9fff]{2,12}$", lines[0]):
                row[key_col] = lines[0]

        for col in template_columns:
            if row.get(col):
                continue
            for alias in _column_aliases(col):
                # 优先匹配「字段：数值」，避免短别名（如 GDP）误命中「人均GDP」
                patterns = [
                    rf"(?<![\u4e00-\u9fffA-Za-z]){re.escape(alias)}\s*[：:]\s*([\d,\.]+)",
                    rf"(?<![\u4e00-\u9fffA-Za-z]){re.escape(alias)}\s*[为是]\s*([\d,\.]+)",
                ]
                if len(_normalize_label(alias)) >= 4:
                    patterns.append(
                        rf"(?<![\u4e00-\u9fffA-Za-z]){re.escape(alias)}\s*([\d,\.]+)\s*(?:亿元|万|元|人|万人)?"
                    )
                for pat in patterns:
                    match = re.search(pat, block, flags=re.IGNORECASE)
                    if match:
                        row[col] = match.group(1).replace(",", "").strip()
                        break
                if row.get(col):
                    break

        if not row.get(key_col):
            for col in template_columns:
                if row.get(col):
                    continue
                norm_col = _normalize_label(col)
                for alias_key, mapped_col in alias_map.items():
                    if mapped_col != col:
                        continue
                    for alias in _column_aliases(col):
                        if _normalize_label(alias) != alias_key:
                            continue
                        match = re.search(
                            rf"{re.escape(alias)}\s*[：:]\s*([\d,\.]+)",
                            block,
                            flags=re.IGNORECASE,
                        )
                        if match:
                            row[col] = match.group(1).replace(",", "").strip()
                            break

        if len(block) > 600 and not row.get(key_col):
            continue

        filled = sum(1 for col in template_columns if str(row.get(col, "")).strip())
        if key_col and any(token in key_col for token in ("城市", "地区", "国家", "省份")):
            if not str(row.get(key_col, "")).strip():
                continue
            if filled < max(2, len(template_columns) // 2):
                continue
        elif filled < max(2, len(template_columns) // 2):
            continue

        records.append({col: str(row.get(col, "")).strip() for col in template_columns})

    return _dedupe_records(records, key_col)


def _search_num(text: str, patterns: List[str]) -> str:
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).replace(",", "").strip()
    return ""


def _find_column(template_columns: List[str], *keywords: str) -> str:
    for col in template_columns:
        norm = _normalize_label(col)
        if all(_normalize_label(kw) in norm or kw in col for kw in keywords):
            return col
    for col in template_columns:
        if any(kw in col for kw in keywords):
            return col
    return ""


def _is_city_economy_template(template_columns: List[str]) -> bool:
    labels = "".join(template_columns)
    return "城市" in labels and "GDP" in labels.upper()


def _is_region_narrative_template(template_columns: List[str]) -> bool:
    labels = "".join(template_columns)
    return ("地区" in labels or "国家" in labels) and "人口" in labels


def _extract_inline_city_records(text: str, template_columns: List[str]) -> List[Dict[str, str]]:
    """单行内联：青岛 GDP 总量 17,603.50 亿元，常住人口 1,032.80 万…"""
    if not _is_city_economy_template(template_columns):
        return []

    key_col = _guess_key_column(template_columns)
    gdp_col = next(
        (c for c in template_columns if "gdp" in _normalize_label(c) and "人均" not in c),
        "",
    )
    pop_col = next((c for c in template_columns if "人口" in c), "")
    pgdp_col = next(
        (c for c in template_columns if "人均" in c and "gdp" in _normalize_label(c)),
        "",
    )
    rev_col = next((c for c in template_columns if "预算收入" in c), "")
    skip_names = {
        "中国", "我国", "全国", "经济", "数据", "报告", "结语", "来源", "排名",
        "第二", "第三", "第四", "当日", "当日各",
    }
    records: List[Dict[str, str]] = []

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if len(line) < 24 or "GDP" not in line.upper():
            continue

        city = ""
        head = re.match(r"^([\u4e00-\u9fff]{2,8})", line)
        if head:
            city = head.group(1)
        if city in skip_names:
            continue
        if not re.search(r"GDP\s*总量|亿元.*GDP\s*总量", line, flags=re.IGNORECASE):
            continue

        gdp = _search_num(
            line,
            [
                r"GDP\s*总量\s*(?:达到\s*)?([\d,\.]+)\s*亿元",
                r"([\d,\.]+)\s*亿元\s*的\s*GDP\s*总量",
                r"([\d,\.]+)\s*亿元\s*GDP\s*总量",
            ],
        )
        pop = _search_num(
            line,
            [
                r"常住人口(?:达|为)?\s*([\d,\.]+)\s*万",
                r"([\d,\.]+)\s*万\s*常住人口",
                r"人口(?:严控至|规模)?\s*([\d,\.]+)\s*万",
                r"人口\s*([\d,\.]+)\s*万",
            ],
        )
        pgdp = _search_num(
            line,
            [
                r"人均\s*GDP\s*(?:高达|为)?\s*([\d,\.]+)\s*元",
                r"([\d,\.]+)\s*元.*?人均\s*GDP",
            ],
        )
        rev = _search_num(
            line,
            [
                r"一般公共预算收入\s*(?:突破|增长至|达|高达)?\s*([\d,\.]+)\s*亿元",
                r"一般公共预算收入\s*([\d,\.]+)\s*亿元",
            ],
        )

        row = {col: "" for col in template_columns}
        if key_col:
            row[key_col] = city
        if gdp_col and gdp:
            row[gdp_col] = gdp
        if pop_col and pop:
            row[pop_col] = pop
        if pgdp_col and pgdp:
            row[pgdp_col] = pgdp
        if rev_col and rev:
            row[rev_col] = rev

        filled = sum(1 for value in row.values() if str(value).strip())
        if city and filled >= 3:
            records.append(row)

    return _dedupe_records(records, key_col)


def _extract_province_narrative_records(text: str, template_columns: List[str]) -> List[Dict[str, str]]:
    """省份叙述段：湖北省常住人口约 5775 万人，人均 GDP 约 7.3 万元…"""
    if not _is_region_narrative_template(template_columns):
        return []

    region_col = _find_column(template_columns, "地区") or _find_column(template_columns, "国家") or template_columns[0]
    continent_col = _find_column(template_columns, "大洲")
    pgdp_col = _find_column(template_columns, "人均", "gdp")
    pop_col = _find_column(template_columns, "人口")
    daily_col = _find_column(template_columns, "检测")
    cases_col = _find_column(template_columns, "病例")

    default_continent = "亚洲" if ("亚洲" in text or "Asia" in text) else ""

    records: List[Dict[str, str]] = []
    for block in re.split(r"(?=[\u4e00-\u9fff]{2,15}(?:省|市|自治区))", text):
        block = block.strip()
        if len(block) < 20:
            continue
        region_match = re.match(r"^([\u4e00-\u9fff]{2,15}(?:省|市|自治区))", block)
        if not region_match:
            continue
        region = region_match.group(1)

        pop = _search_num(
            block,
            [
                r"常住人口约?\s*([\d,\.]+)\s*万",
                r"人口约?\s*([\d,\.]+)\s*万",
                r"人口\s*([\d,\.]+)\s*万",
            ],
        )
        pgdp = _search_num(
            block,
            [
                r"人均\s*GDP\s*约?\s*([\d,\.]+)\s*万",
                r"人均\s*GDP\s*达?\s*([\d,\.]+)\s*万",
                r"人均\s*GDP\s*([\d,\.]+)\s*万",
            ],
        )
        daily = _search_num(
            block,
            [
                r"核酸检测量约?\s*([\d,\.]+)\s*万份",
                r"检测量约?\s*([\d,\.]+)\s*万份",
                r"检测量.*?(?:达|约)?\s*([\d,\.]+)\s*万份",
            ],
        )

        cases = ""
        case_match = re.search(r"新增\s*(\d+)\s*例(?:本土)?确诊", block)
        if case_match:
            cases = case_match.group(1)
        elif re.search(r"新增\s*(\d+)\s*例", block):
            cases = re.search(r"新增\s*(\d+)\s*例", block).group(1)
        elif any(token in block for token in ("零新增", "无新增", "全零报告", "无疫情新增", "零新增确诊")):
            cases = "0"

        row = {col: "" for col in template_columns}
        if region_col:
            row[region_col] = region
        if continent_col and default_continent:
            row[continent_col] = default_continent
        if pop_col and pop:
            row[pop_col] = pop
        if pgdp_col and pgdp:
            row[pgdp_col] = pgdp
        if daily_col and daily:
            row[daily_col] = daily
        if cases_col and cases != "":
            row[cases_col] = cases

        filled = sum(1 for value in row.values() if str(value).strip())
        if filled >= 3:
            records.append(row)

    return _dedupe_records(records, region_col)


def _score_entity_records(records: List[Dict[str, str]], key_col: str) -> float:
    if not records:
        return 0.0
    count = len(records)
    keyed = sum(1 for row in records if key_col and str(row.get(key_col, "")).strip())
    key_ratio = keyed / count if key_col else 1.0
    avg_filled = sum(sum(1 for value in row.values() if str(value).strip()) for row in records) / count
    return count * 10.0 + key_ratio * 8.0 + avg_filled


def _pick_best_rule_entities(
    text: str,
    template_columns: List[str],
) -> Tuple[List[Dict[str, str]], str]:
    key_col = _guess_key_column(template_columns)
    candidates = [
        ("inline_city", _extract_inline_city_records(text, template_columns)),
        ("province_narrative", _extract_province_narrative_records(text, template_columns)),
        ("labeled", _extract_labeled_records(text, template_columns)),
    ]
    best_name = "labeled"
    best_rows: List[Dict[str, str]] = []
    best_score = -1.0
    for name, rows in candidates:
        score = _score_entity_records(rows, key_col)
        if score > best_score:
            best_score = score
            best_name = name
            best_rows = rows
    return best_rows, best_name


def _build_extraction_hints(
    instruction: str,
    template_columns: List[str],
    entities: List[Dict[str, str]],
    extract_source: str,
) -> str:
    hints: List[str] = []
    inst = instruction or ""
    has_date_intent = bool(re.search(r"\d{4}[/年\-]\d{1,2}|从.*到|日期|筛选|过滤", inst))
    has_date_col = any("日期" in col for col in template_columns)
    only_narrative_day = bool(re.search(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", inst))

    if has_date_intent and not has_date_col:
        hints.append(
            "模板中没有「日期」列，且 Word 叙述文档无法像 Excel 那样按日期范围精确筛行。"
            "若需按 2020/7/1～8/31 填表，请改用「COVID Excel 数据集 + 模板」，模式选「提取与填表」。"
        )
    elif has_date_intent and only_narrative_day and extract_source == "province_narrative":
        hints.append(
            "当前 Word 为某日纪实快照，无法覆盖 7/1～8/31 全时段；已提取各省当日可解析字段。"
        )

    if not entities:
        if _is_region_narrative_template(template_columns):
            hints.append(
                "未能从 Word 中解析出与模板匹配的行。疫情按日期填表请使用 Excel 数据源（如 COVID 全球数据集.xlsx）+ 模板。"
            )
        elif _is_city_economy_template(template_columns):
            hints.append(
                "未能识别城市经济数据。请确认 Word 中含「城市名 GDP 总量 … 亿元，常住人口 … 万」类行。"
            )

    return "\n".join(hints)


def _dedupe_records(records: List[Dict[str, str]], key_col: str) -> List[Dict[str, str]]:
    if not records:
        return []
    if not key_col:
        return records
    merged: Dict[str, Dict[str, str]] = {}
    extras: List[Dict[str, str]] = []
    for row in records:
        key = str(row.get(key_col, "")).strip()
        if not key:
            extras.append(row)
            continue
        if key not in merged:
            merged[key] = dict(row)
            continue
        for col, val in row.items():
            if val and not str(merged[key].get(col, "")).strip():
                merged[key][col] = val
    return list(merged.values()) + extras


class AgentB(BaseAgent):
    """
    Agent_B: 实体提取

    能力：
    - 理解自然语言
    - 根据用户要求和表格模板（可选）
    - 从非结构化数据中提取所需数据为JSON格式
    - 支持格式: word, md, txt
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        super().__init__(config or get_config())
        self.name = "Agent_B"
        self.agent_type = "extraction"
        self.logger = get_logger(__name__)
        self.model = self._init_extraction_model()

    def execute(self, task_spec: TaskSpec, progress_callback=None, **kwargs) -> AgentResponse:
        """
        执行实体提取任务
        """
        # 验证输入
        is_valid, error_msg = self.validate_input(task_spec)
        if not is_valid:
            return AgentResponse(success=False, message=error_msg)

        try:
            return self._extract_entities(task_spec, progress_callback=progress_callback)
        except Exception as e:
            return AgentResponse(
                success=False,
                message=f"提取失败: {str(e)}"
            )

    def _extract_entities(self, task_spec: TaskSpec, progress_callback=None) -> AgentResponse:
        """提取实体数据。"""
        from config import get_config

        self.config = get_config()
        self.model = self._init_extraction_model()

        input_text = self._resolve_input_text(task_spec)
        if not input_text.strip():
            return AgentResponse(success=False, message="源文件解析结果为空")

        template_columns = self._load_template_columns(task_spec)
        if not template_columns:
            return AgentResponse(success=False, message="模板未识别到有效列名")

        schema = self._build_extraction_schema(
            instruction=task_spec.instruction,
            template_columns=template_columns,
        )

        key_col = _guess_key_column(template_columns)
        allow_rule_fallback = os.getenv("ALLOW_RULE_EXTRACTION_FALLBACK", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        if not self.model:
            return AgentResponse(
                success=False,
                message=(
                    "实体提取需要大模型参与：请在「设置」中选择「小米 MiMo」，"
                    "填写 API Key，模型填 mimo-v2.5，Base URL 填 https://token-plan-cn.xiaomimimo.com/v1"
                ),
            )

        llm_entities: List[Dict[str, Any]] = []
        chunk_count = 0
        total_extractions = 0
        if progress_callback:
            progress_callback(0, 1, "正在调用大模型理解文档并提取实体…")
        llm_error: Optional[str] = None
        try:
            llm_entities, chunk_count, total_extractions = self._extract_from_chunks(
                input_text=input_text,
                template_columns=template_columns,
                fields=schema["fields"],
                instruction=task_spec.instruction,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            llm_error = str(exc)
            self.logger.warning(f"LLM 分块抽取失败: {exc}")

        llm_flat = self._flatten_entities(llm_entities, template_columns, schema.get("mapping", {}))

        if llm_flat:
            entities = llm_flat
            extract_source = "llm"
        elif allow_rule_fallback:
            rule_entities, rule_source = _pick_best_rule_entities(input_text, template_columns)
            if rule_entities:
                entities = rule_entities
                extract_source = f"rule:{rule_source}"
            else:
                entities = []
                extract_source = "none"
        else:
            detail = llm_error or "大模型未返回有效实体"
            return AgentResponse(
                success=False,
                message=(
                    f"大模型提取失败：{detail}。"
                    "请检查 MiMo API Key、网络与模型配置；演示场景禁止静默规则兜底。"
                ),
            )

        entities = _dedupe_records(entities, key_col)
        hints = _build_extraction_hints(
            task_spec.instruction,
            template_columns,
            entities,
            extract_source,
        )
        if extract_source == "llm":
            message = f"实体提取完成（大模型参与），共 {len(entities)} 条记录"
        elif extract_source.startswith("rule"):
            message = f"实体提取完成（规则兜底，模型未返回有效结果），共 {len(entities)} 条记录"
        else:
            message = f"实体提取完成，共 {len(entities)} 条记录"
        if hints:
            message = f"{message}\n{hints}"

        return AgentResponse(
            success=True,
            message=message,
            data={
                "entities": entities,
                "schema": schema,
                "chunk_count": chunk_count,
                "total_extractions": total_extractions,
                "extract_source": extract_source,
                "hints": hints,
            },
        )

    def _init_extraction_model(self):
        """初始化 langextract 模型，按 LLM_PROVIDER 动态选择 provider。"""
        try:
            from langextract import factory
            # 导入 providers 包以触发 provider 注册
            from core.llm import providers  # noqa: F401
        except Exception as exc:
            self.logger.error(f"langextract 初始化失败: {exc}")
            return None

        model_id = self.config.llm.model or "deepseek-chat"
        llm_provider = (self.config.llm.provider or os.getenv("LLM_PROVIDER") or "deepseek").strip().lower()

        # 优先按显式 provider 选择；若 provider 未识别，则按模型名前缀自动推断
        provider_kwargs: Dict[str, Any] = {}
        if llm_provider in ("zhipu", "glm"):
            provider_name = "ZhipuLanguageModel"
            api_key = os.getenv("ZHIPU_API_KEY") or self.config.llm.api_key
        elif llm_provider == "mimo":
            provider_name = "MimoLanguageModel"
            api_key = os.getenv("MIMO_API_KEY") or self.config.llm.api_key
            base_url = self.config.llm.base_url or os.getenv("MIMO_BASE_URL")
            if base_url:
                provider_kwargs["base_url"] = base_url
        elif llm_provider == "deepseek":
            provider_name = "DeepSeekLanguageModel"
            api_key = os.getenv("DEEPSEEK_API_KEY") or self.config.llm.api_key
        elif str(model_id).lower().startswith("glm"):
            provider_name = "ZhipuLanguageModel"
            api_key = os.getenv("ZHIPU_API_KEY") or self.config.llm.api_key
        elif str(model_id).lower().startswith("mimo"):
            provider_name = "MimoLanguageModel"
            api_key = os.getenv("MIMO_API_KEY") or self.config.llm.api_key
            base_url = self.config.llm.base_url or os.getenv("MIMO_BASE_URL")
            if base_url:
                provider_kwargs["base_url"] = base_url
        else:
            provider_name = "DeepSeekLanguageModel"
            api_key = os.getenv("DEEPSEEK_API_KEY") or self.config.llm.api_key

        if not api_key:
            self.logger.warning(f"未检测到提取模型 API Key(provider={provider_name})，后续将回退到规则抽取")
            return None

        provider_kwargs["api_key"] = api_key
        model_config = factory.ModelConfig(
            model_id=model_id,
            provider=provider_name,
            provider_kwargs=provider_kwargs,
        )
        return factory.create_model(model_config)

    def _resolve_input_text(self, task_spec: TaskSpec) -> str:
        """优先读取预解析内容，缺失时回退本地读取。"""
        from utils.document_reader import read_document

        parsed_content = task_spec.parameters.get("parsed_content")
        if isinstance(parsed_content, dict) and parsed_content:
            text_parts = [str(v) for v in parsed_content.values() if isinstance(v, str)]
            text = "\n\n".join(text_parts).strip()
            if text:
                return text

        texts: List[str] = []
        for source in task_spec.source_files:
            content = read_document(source.path)
            if content and not content.startswith("Error"):
                texts.append(content)

        return "\n\n".join(texts)

    def _load_template_columns(self, task_spec: TaskSpec) -> List[str]:
        return read_excel_template_columns(task_spec.template_file.path)

    def _build_extraction_schema(self, instruction: str, template_columns: List[str]) -> Dict[str, Any]:
        """抽取字段固定为模板列名，避免 LLM 改写列名导致匹配失败。"""
        alias_mapping: Dict[str, str] = {}
        for col in template_columns:
            for alias in _column_aliases(col):
                alias_mapping[alias] = col
        return {
            "fields": template_columns,
            "types": ["str" for _ in template_columns],
            "mapping": {c: c for c in template_columns},
            "alias_mapping": alias_mapping,
        }

    def _flatten_entities(
        self,
        entities: List[Dict[str, Any]],
        template_columns: List[str],
        field_mapping: Dict[str, str],
    ) -> List[Dict[str, str]]:
        alias_map = _build_alias_to_column(template_columns)
        flat_rows: List[Dict[str, str]] = []

        for raw in entities or []:
            if not isinstance(raw, dict):
                continue
            row: Dict[str, str] = {col: "" for col in template_columns}
            for key, value in raw.items():
                mapped_key = field_mapping.get(key, key)
                target = _resolve_field_name(str(mapped_key), template_columns, alias_map)
                if not target:
                    target = _resolve_field_name(str(key), template_columns, alias_map)
                if not target:
                    continue
                if isinstance(value, list):
                    cell = str(value[0]).strip() if value else ""
                else:
                    cell = str(value or "").strip()
                if cell:
                    row[target] = cell

            filled = sum(1 for col in template_columns if row.get(col))
            key_col = _guess_key_column(template_columns)
            if filled >= max(2, len(template_columns) // 2) or (row.get(key_col) and filled >= 1):
                flat_rows.append(row)

        return _dedupe_records(flat_rows, _guess_key_column(template_columns))

    def _safe_load_json(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^```", "", text)
        text = re.sub(r"```$", "", text).strip()

        match = re.search(r"\{[\s\S]*\}", text)
        json_text = match.group(0) if match else text
        return json.loads(json_text)

    def _extract_from_chunks(
        self,
        input_text: str,
        template_columns: List[str],
        fields: List[str],
        instruction: str,
        progress_callback=None,
    ) -> Tuple[List[Dict[str, List[str]]], int, int]:
        if not self.model:
            return [], 0, 0

        import langextract as lx
        from langextract.core import tokenizer

        from config import get_config

        max_workers = max(1, get_config().processing.extraction_max_workers)
        chunk_size = int(os.getenv("EXTRACTION_CHUNK_SIZE", "3000"))
        chunks_with_offset = split_text_semantic_with_offset(input_text, chunk_size)
        alias_map = _build_alias_to_column(template_columns)

        # 立即通知前端任务已启动（此时文本已分块完毕，后端开始并发抽取）
        if progress_callback:
            progress_callback(
                0,
                len(chunks_with_offset),
                f"大模型提取中（{len(chunks_with_offset)} 个文本分块）…",
            )

        prompt_description = f"""
从文本中提取以下字段（字段名必须与下列名称完全一致，每条记录对应一个城市/主体）：
{fields}

要求：
{instruction or "按模板列名逐条提取，每个城市/主体输出一行，数值只保留数字。"}

注意：
1. extraction_class 必须使用上面列出的完整字段名（含括号单位）。
2. 同一分块内多个城市请分别输出多组字段。
3. 缺失字段可留空，但城市名/主体名必须尽量提取。
"""

        key_col = _guess_key_column(template_columns)
        examples = [
            lx.data.ExampleData(
                text=(
                    "青岛\nGDP总量（亿元）：16900\n常住人口（万）：1020\n"
                    "人均GDP（元）：165000\n一般公共预算收入（亿元）：1200"
                ),
                extractions=[
                    lx.data.Extraction(key_col or fields[0], "青岛"),
                    lx.data.Extraction(fields[1] if len(fields) > 1 else "GDP总量（亿元）", "16900"),
                    lx.data.Extraction(fields[2] if len(fields) > 2 else "常住人口（万）", "1020"),
                ],
            )
        ]
        unicode_tokenizer = tokenizer.UnicodeTokenizer()

        # 注意：progress_callback 是普通函数，直接在当前线程调用即可
        # queue.Queue.put_nowait() 本身是线程安全的

        all_entities: List[Dict[str, List[str]]] = []
        total_extractions = 0
        total_chunks = len(chunks_with_offset)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self._extract_single_chunk,
                    chunk,
                    offset,
                    template_columns,
                    fields,
                    alias_map,
                    prompt_description,
                    examples,
                    unicode_tokenizer,
                    lx,
                )
                for chunk, offset in chunks_with_offset
            ]

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result["status"] == "success":
                    total_extractions += result["extractions_count"]
                    all_entities.extend(result["entities"])
                else:
                    self.logger.warning(f"分块抽取失败: {result['error']}")

                # 分块完成回调：直接在当前线程执行（queue.Queue 线程安全）
                if progress_callback:
                    msg = f"分块 {i}/{total_chunks}，已提取 {len(all_entities)} 条"
                    progress_callback(i, total_chunks, msg)

        return all_entities, len(chunks_with_offset), total_extractions

    def _extract_single_chunk(
        self,
        chunk: str,
        chunk_offset: int,
        template_columns: List[str],
        fields: List[str],
        alias_map: Dict[str, str],
        prompt_description: str,
        examples: List[Any],
        unicode_tokenizer: Any,
        lx_module: Any,
    ) -> Dict[str, Any]:
        """处理单个分块并返回记录列表。"""
        try:
            result = lx_module.extract(
                text_or_documents=chunk,
                prompt_description=prompt_description,
                examples=examples,
                model=self.model,
                tokenizer=unicode_tokenizer,
                max_workers=1,
            )

            data: Dict[str, List[str]] = {}
            pos_data: Dict[str, List[str]] = {}
            for extraction in result.extractions:
                raw_key = getattr(extraction, "extraction_class", None)
                value = getattr(extraction, "extraction_text", None)
                if not raw_key:
                    continue
                key = _resolve_field_name(str(raw_key), template_columns, alias_map) or str(raw_key)

                global_start = None
                global_end = None
                if hasattr(extraction, "char_interval") and extraction.char_interval:
                    global_start = extraction.char_interval.start_pos + chunk_offset
                    global_end = extraction.char_interval.end_pos + chunk_offset

                pos = (
                    f"{global_start}-{global_end}"
                    if global_start is not None and global_end is not None
                    else ""
                )

                data.setdefault(key, []).append(value or "")
                pos_data.setdefault(key, []).append(pos)

            records: List[Dict[str, List[str]]] = []
            num_rows = max((len(v) for v in data.values()), default=0)
            key_col = _guess_key_column(template_columns)
            min_required = max(2, len(fields) // 2)
            for i in range(num_rows):
                row: Dict[str, List[str]] = {}
                filled = 0
                for field in fields:
                    values = data.get(field, [])
                    positions = pos_data.get(field, [])
                    field_value = values[i] if i < len(values) else ""
                    field_pos = positions[i] if i < len(positions) else ""
                    row[field] = [field_value, field_pos]
                    if str(field_value).strip():
                        filled += 1

                has_key = bool(str((row.get(key_col) or ["", ""])[0]).strip()) if key_col else False
                if filled >= min_required or (has_key and filled >= 1):
                    records.append(row)

            return {
                "status": "success",
                "entities": records,
                "extractions_count": len(result.extractions),
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
            }

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """验证输入"""
        if not task_spec.source_files:
            return False, "缺少源文件"

        # 检查是否有模板文件
        if not task_spec.template_file:
            return False, "实体提取模式需要提供Excel模板文件"

        return True, ""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return get_config().agent.get_prompt(self.agent_type)

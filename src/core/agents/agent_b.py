"""
Agent_B: 实体提取Agent
负责从非结构化文档中提取数据为JSON格式
"""
import asyncio
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

        entities, chunk_count, total_extractions = self._extract_from_chunks(
            input_text=input_text,
            fields=schema["fields"],
            instruction=task_spec.instruction,
            progress_callback=progress_callback,
        )

        return AgentResponse(
            success=True,
            message=f"实体提取完成，共提取 {len(entities)} 条记录",
            data={
                "entities": entities,
                "schema": schema,
                "chunk_count": chunk_count,
                "total_extractions": total_extractions,
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
        if llm_provider in ("zhipu", "glm"):
            provider_name = "ZhipuLanguageModel"
            api_key = os.getenv("ZHIPU_API_KEY") or self.config.llm.api_key
        elif llm_provider == "deepseek":
            provider_name = "DeepSeekLanguageModel"
            api_key = os.getenv("DEEPSEEK_API_KEY") or self.config.llm.api_key
        elif str(model_id).lower().startswith("glm"):
            provider_name = "ZhipuLanguageModel"
            api_key = os.getenv("ZHIPU_API_KEY") or self.config.llm.api_key
        else:
            provider_name = "DeepSeekLanguageModel"
            api_key = os.getenv("DEEPSEEK_API_KEY") or self.config.llm.api_key

        if not api_key:
            self.logger.warning(f"未检测到提取模型 API Key(provider={provider_name})，后续将回退到规则抽取")
            return None

        model_config = factory.ModelConfig(
            model_id=model_id,
            provider=provider_name,
            provider_kwargs={"api_key": api_key},
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
        """用模型推断抽取字段，失败时回退模板字段。"""
        fallback = {
            "fields": template_columns,
            "types": ["str" for _ in template_columns],
            "mapping": {c: c for c in template_columns},
        }

        if not self.model:
            return fallback

        schema_prompt = f"""
你是信息抽取专家。

用户需求：
{instruction or "按模板提取"}

模板表头：
{template_columns}

任务：
1. 确定需要抽取的字段
2. 给出字段类型（str/int/float）
3. 建立字段 → Excel列名映射

请输出严格 JSON，结构如下：
{{
  "fields": ["字段1", "字段2"],
  "types": ["str", "int"],
  "mapping": {{"字段1": "模板列名1", "字段2": "模板列名2"}}
}}
不要输出 JSON 以外内容。
"""
        try:
            schema_resp = list(self.model.infer([schema_prompt]))
            schema_text = schema_resp[0][0].output if schema_resp and schema_resp[0] else ""
            parsed = self._safe_load_json(schema_text)
            fields = parsed.get("fields") if isinstance(parsed, dict) else None
            if not fields:
                return fallback

            mapping = parsed.get("mapping") or {f: f for f in fields}
            types = parsed.get("types") or ["str" for _ in fields]
            return {"fields": fields, "types": types, "mapping": mapping}
        except Exception as exc:
            self.logger.warning(f"schema 推断失败，使用模板兜底: {exc}")
            return fallback

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
        fields: List[str],
        instruction: str,
        progress_callback=None,
    ) -> Tuple[List[Dict[str, List[str]]], int, int]:
        if not self.model:
            raise RuntimeError("提取模型未初始化，请检查 LLM_PROVIDER 与 API Key")

        import langextract as lx
        from langextract.core import tokenizer

        from config import get_config

        max_workers = max(1, get_config().processing.extraction_max_workers)
        chunk_size = int(os.getenv("EXTRACTION_CHUNK_SIZE", "500"))
        chunks_with_offset = split_text_semantic_with_offset(input_text, chunk_size)

        # 立即通知前端任务已启动（此时文本已分块完毕，后端开始并发抽取）
        if progress_callback:
            progress_callback(0, len(chunks_with_offset), f"开始提取 {len(chunks_with_offset)} 个分块...")

        prompt_description = f"""
从文本中提取以下字段：
{fields}

要求：
{instruction}


⚠️ 如果当前文本缺少某些字段（如城市名），请结合上下文合理补全。

"""

        examples = [
            lx.data.ExampleData(
                text="我叫小明，今年30岁，身高1.75米。",
                extractions=[
                    lx.data.Extraction("姓名", "小明"),
                    lx.data.Extraction("年龄", "30"),
                    lx.data.Extraction("身高", "1.75"),
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
                    fields,
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
        fields: List[str],
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
                key = getattr(extraction, "extraction_class", None)
                value = getattr(extraction, "extraction_text", None)
                if not key:
                    continue

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
            for i in range(num_rows):
                row: Dict[str, List[str]] = {}
                row_complete = True
                for field in fields:
                    values = data.get(field, [])
                    positions = pos_data.get(field, [])
                    field_value = values[i] if i < len(values) else ""
                    field_pos = positions[i] if i < len(positions) else ""
                    row[field] = [field_value, field_pos]
                    if not str(field_value).strip():
                        row_complete = False

                if row_complete:
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

"""
工作流协调器
核心编排模块，根据任务类型选择并执行对应工作流
"""
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
import json
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook

from .task_spec import TaskSpec, TaskType, FileInfo
from .executor import TaskExecutor
from config import SystemConfig, get_config
from core.storage import build_blob_name, upload_file_to_storage
from db.session_repository import add_session_file, get_session_by_id
from db.workflow_persistence import (
    persist_workflow_execute_begin,
    persist_workflow_execute_end,
)
from output.result_handler import ResultHandler
from utils.logger import get_logger


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool
    message: str
    data: Optional[Any] = None
    output_file: Optional[str] = None
    # 交互式 Agent 实例（用于文档理解模式）
    interactive_agent: Optional[Any] = None
    # 源文件列表
    source_files: Optional[List[Any]] = None


class WorkflowCoordinator:
    """
    工作流协调器
    负责路由和管理不同类型任务的执行流程
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        self.executor = TaskExecutor(self.config)
        self.result_handler = ResultHandler(self.config.output_dir)
        self._workflow_handlers: Dict[TaskType, Callable] = {}
        self._register_workflows()
        # 保存 DocumentAgent 实例供交互式对话使用
        self._document_agent_instance = None

    def _register_workflows(self):
        """注册所有工作流处理器"""
        self._workflow_handlers = {
            TaskType.DEFAULT_CONVERSATION: self._default_conversation_flow,
            TaskType.DOCUMENT_UNDERSTANDING: self._document_understanding_flow,
            TaskType.DOCUMENT_EDITING: self._document_editing_flow,
            TaskType.ENTITY_EXTRACTION: self._entity_extraction_flow,
            TaskType.TABLE_FILLING: self._table_filling_flow,
            TaskType.WORKFLOW_PIPELINE: self._workflow_pipeline_flow,
        }

    def execute(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        执行工作流
        根据任务规格选择对应的工作流并执行
        """
        self.logger.info(f"开始执行任务: {task_spec.task_type.value}")

        # 验证任务规格
        is_valid, error_msg = task_spec.validate()
        if not is_valid:
            self.logger.error(f"任务规格验证失败: {error_msg}")
            return WorkflowResult(success=False, message=error_msg)

        persist_workflow_execute_begin(task_spec, self.config)

        handler = self._workflow_handlers.get(task_spec.task_type)
        if not handler:
            msg = f"不支持的任务类型: {task_spec.task_type.value}"
            persist_workflow_execute_end(task_spec, False, msg, self.config)
            return WorkflowResult(success=False, message=msg)

        try:
            result = handler(task_spec, progress_callback=progress_callback)
            self._persist_generated_file(task_spec, result)
            persist_workflow_execute_end(
                task_spec, result.success, result.message, self.config
            )
            return result
        except Exception as e:
            self.logger.error(f"工作流执行失败: {str(e)}")
            persist_workflow_execute_end(task_spec, False, str(e), self.config)
            return WorkflowResult(success=False, message=f"执行失败: {str(e)}")

    def _default_conversation_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        默认对话模式
        直接与LLM交流，查询系统信息
        """
        self.logger.info("进入默认对话模式")

        result = self.executor.execute_agent(
            agent_name="conversation",
            task_spec=task_spec
        )

        return WorkflowResult(
            success=True,
            message=result.message,
            data=result
        )

    def _document_understanding_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        文档理解模式
        1. 初始化 DocumentAgent
        2. 设置文档（如果有）
        3. 返回可交互的 Agent 实例供 CLI 使用
        """
        self.logger.info("进入文档理解模式")

        # 获取 DocumentAgent 实例
        agent = self.executor._get_agent("document_understanding")
        if not agent:
            return WorkflowResult(
                success=False,
                message="DocumentAgent 初始化失败"
            )

        # 设置文档（如果有）
        if task_spec.source_files:
            agent.set_documents(task_spec.source_files)
            file_names = [f.name for f in task_spec.source_files]
        else:
            file_names = []

        # 保存实例供交互式对话使用
        self._document_agent_instance = agent

        return WorkflowResult(
            success=True,
            message="文档理解 Agent 已就绪，可以开始对话",
            data={"status": "ready", "files": file_names},
            interactive_agent=agent,
            source_files=task_spec.source_files or []
        )

    def _document_editing_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        文档编辑模式
        1. 解析文档
        2. Agent_A 按要求编辑文档
        """
        self.logger.info("进入文档编辑模式")

        # 1. 解析文档
        parsed_content = self.executor.parse_documents(task_spec.source_files)

        # 2. Agent_A 编辑文档
        task_spec.parameters["parsed_content"] = parsed_content
        result = self.executor.execute_agent(
            agent_name="agent_a",
            task_spec=task_spec,
            mode="editing"
        )

        output_file = task_spec.output_file
        inner_data = getattr(result, "data", None)
        if isinstance(inner_data, dict):
            output_file = inner_data.get("output_file") or output_file

        message = getattr(result, "message", None) or "文档编辑完成，已生成可下载文件"
        success = bool(getattr(result, "success", True))
        if isinstance(inner_data, dict) and inner_data.get("edited") is False:
            success = False

        return WorkflowResult(
            success=success,
            message=message,
            data=result,
            output_file=output_file
        )

    def _entity_extraction_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        实体提取模式
        1. 解析文档
        2. Agent_B 提取实体数据为JSON
        3. 将数据填入模板
        4. 可选存入数据库
        """
        self.logger.info("进入实体提取模式")

        # 文档解析完毕后立即通知前端，让用户知道任务已启动
        if progress_callback:
            progress_callback(0, 1, "文档解析完成，开始提取...")

        # 1. 解析非结构化文档
        parsed_content = self.executor.parse_documents(task_spec.source_files)

        # 2. Agent_B 提取实体（带进度回调）
        task_spec.parameters["parsed_content"] = parsed_content
        extracted_data = self.executor.execute_agent(
            agent_name="agent_b",
            task_spec=task_spec,
            progress_callback=progress_callback,
        )

        if not extracted_data or not getattr(extracted_data, "success", False):
            err_msg = getattr(extracted_data, "message", "实体提取失败")
            return WorkflowResult(success=False, message=err_msg, data=extracted_data)

        output_filename = (
            Path(task_spec.output_file).name
            if task_spec.output_file
            else f"entity_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        payload = getattr(extracted_data, "data", {})
        if not isinstance(payload, dict):
            payload = {}

        saved_json_path = self.result_handler.save_json(
            data=getattr(extracted_data, "data", {}),
            filename=output_filename,
        )
        saved_xlsx_path = self._save_entities_xlsx(
            payload,
            Path(output_filename).with_suffix(".xlsx").name,
        )

        generated_paths = [p for p in (saved_json_path, saved_xlsx_path) if p]
        if generated_paths:
            extracted_data.metadata = extracted_data.metadata or {}
            extracted_data.metadata["generated_file_paths"] = generated_paths
            extracted_data.message = "实体提取完成，已生成可下载文件"

        # 3. 填入模板
        filled_template = ""
        if task_spec.template_file:
            filled_template = self.executor.fill_template(
                data=extracted_data,
                template=task_spec.template_file
            )
            if filled_template:
                extracted_data.metadata = extracted_data.metadata or {}
                generated = extracted_data.metadata.get("generated_file_paths")
                if not isinstance(generated, list):
                    generated = []
                if filled_template not in generated:
                    generated.append(filled_template)
                extracted_data.metadata["generated_file_paths"] = generated

        # 4. 可选入库（仅在显式开启 store_to_db 且数据库启用时执行）
        db_message = ""
        should_store_to_db = bool(task_spec.parameters.get("store_to_db")) and bool(self.config.database.enabled)
        if should_store_to_db:
            payload_fields = payload.get("schema", {}).get("fields", []) if isinstance(payload, dict) else []
            payload_entities = payload.get("entities", []) if isinstance(payload, dict) else []
            if not isinstance(payload_fields, list):
                payload_fields = []
            if not payload_fields and isinstance(payload_entities, list) and payload_entities and isinstance(payload_entities[0], dict):
                payload_fields = list(payload_entities[0].keys())
            db_payload = {
                "fields": payload_fields,
                "entities": payload_entities if isinstance(payload_entities, list) else [],
                "schema_version": "1.0.0",
            }
            if task_spec.parameters.get("task_id"):
                db_payload["task_id"] = str(task_spec.parameters.get("task_id"))

            db_task_spec = TaskSpec(
                task_type=task_spec.task_type,
                instruction=task_spec.instruction,
                source_files=task_spec.source_files,
                template_file=task_spec.template_file,
                output_file=task_spec.output_file,
                parameters={"data": db_payload},
                conversation_history=task_spec.conversation_history,
                session_id=task_spec.session_id,
            )
            db_result = self.executor.execute_agent(agent_name="agent_c", task_spec=db_task_spec)
            if getattr(db_result, "success", False):
                db_message = "，并已写入数据库"
                db_data = getattr(db_result, "data", {})
                db_info = {
                    "success": True,
                    "task_uuid": db_data.get("task_uuid") if isinstance(db_data, dict) else None,
                    "extraction_id": db_data.get("extraction_id") if isinstance(db_data, dict) else None,
                    "result_version": db_data.get("result_version") if isinstance(db_data, dict) else None,
                }
                extracted_data.metadata = extracted_data.metadata or {}
                extracted_data.metadata["db_result"] = db_info
                if isinstance(getattr(extracted_data, "data", None), dict):
                    extracted_data.data["db_result"] = db_info
            else:
                self.logger.warning(f"实体提取入库失败: {getattr(db_result, 'message', '')}")
                db_message = "（数据库写入失败，已保留本地输出）"
                db_meta = getattr(db_result, "metadata", None)
                db_error_code = db_meta.get("error_code") if isinstance(db_meta, dict) else None
                fail_info = {
                    "success": False,
                    "error_code": db_error_code,
                    "message": getattr(db_result, "message", "数据库写入失败"),
                }
                extracted_data.metadata = extracted_data.metadata or {}
                extracted_data.metadata["db_result"] = fail_info
                if isinstance(getattr(extracted_data, "data", None), dict):
                    extracted_data.data["db_result"] = fail_info

        return WorkflowResult(
            success=True,
            message=f"实体提取完成{db_message}",
            data=extracted_data,
            output_file=filled_template or saved_json_path or saved_xlsx_path or task_spec.output_file,
        )

    def _save_entities_xlsx(self, payload: Dict[str, Any], filename: str) -> str:
        """将实体提取结果另存为 xlsx，便于直接下载分析。"""
        output_path = Path(self.config.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entities = payload.get("entities", []) if isinstance(payload, dict) else []
        schema = payload.get("schema", {}) if isinstance(payload, dict) else {}
        fields = schema.get("fields", []) if isinstance(schema, dict) else []

        if not isinstance(entities, list):
            entities = []
        if not isinstance(fields, list):
            fields = []
        if not fields and entities and isinstance(entities[0], dict):
            fields = list(entities[0].keys())

        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "entities"

            headers = ["序号", *fields]
            ws.append(headers)

            for idx, row in enumerate(entities, start=1):
                if not isinstance(row, dict):
                    continue
                values = [idx]
                for field in fields:
                    values.append(self._to_excel_cell(row.get(field)))
                ws.append(values)

            wb.save(output_path)
            return str(output_path)
        except Exception as exc:
            self.logger.warning(f"保存实体提取 xlsx 失败: {exc}")
            return ""

    @staticmethod
    def _to_excel_cell(value: Any) -> Any:
        if isinstance(value, list):
            if not value:
                return ""
            return value[0]
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else value

    def _table_filling_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        表格填表模式
        1. Agent_D 筛选Excel数据
        2. 填入表格模板
        """
        self.logger.info("进入表格填表模式")

        # Agent_D 处理表格
        result = self.executor.execute_agent(
            agent_name="agent_d",
            task_spec=task_spec,
            progress_callback=progress_callback,
        )

        return WorkflowResult(
            success=True,
            message="表格填表完成",
            data=result,
            output_file=task_spec.output_file
        )

    def _workflow_pipeline_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        工作流编排模式（统一入口）：
        由 executor 执行节点流水线，coordinator 负责统一结果封装。
        """
        self.logger.info("进入工作流编排模式")
        result = self.executor.execute_workflow_pipeline(task_spec, progress_callback=progress_callback)
        if not isinstance(result, dict) or not result.get("success"):
            message = result.get("message", "工作流执行失败") if isinstance(result, dict) else "工作流执行失败"
            return WorkflowResult(success=False, message=message, data=result)
        return WorkflowResult(
            success=True,
            message=result.get("message", "工作流执行完成"),
            data=result,
            output_file=result.get("output_file"),
        )

    def _persist_generated_file(self, task_spec: TaskSpec, result: WorkflowResult) -> None:
        """将工作流生成的输出文件登记到会话文件表，供会话历史统一查看。"""
        if not task_spec.session_id:
            return

        candidate_paths: List[str] = []
        if result.output_file:
            candidate_paths.append(str(result.output_file))

        agent_response = result.data
        if agent_response is not None:
            metadata = getattr(agent_response, "metadata", None)
            if isinstance(metadata, dict):
                extra_files = metadata.get("generated_file_paths")
                if isinstance(extra_files, list):
                    candidate_paths.extend([str(p) for p in extra_files if p])

            inner_data = getattr(agent_response, "data", None)
            if isinstance(inner_data, dict):
                for key in ("output_file", "output_json", "template_output", "excel_path"):
                    if inner_data.get(key):
                        candidate_paths.append(str(inner_data[key]))

        # 去重并过滤空值
        dedup_paths: List[str] = []
        seen = set()
        for p in candidate_paths:
            pp = str(p).strip()
            if not pp or pp in seen:
                continue
            seen.add(pp)
            dedup_paths.append(pp)

        if not dedup_paths:
            return

        session = get_session_by_id(task_spec.session_id, config=self.config)
        if not session:
            return
        try:
            task_uuid = task_spec.parameters.get("task_uuid")
            for output_file in dedup_paths:
                path = Path(output_file)
                if not path.exists():
                    continue
                storage_key = None
                try:
                    storage_key = upload_file_to_storage(
                        path,
                        config=self.config,
                        blob_name=build_blob_name(task_spec.session_id, path.name, prefix=self.config.storage.object_key_prefix),
                    )
                except Exception:
                    storage_key = None
                add_session_file(
                    session_id=task_spec.session_id,
                    file_name=path.name,
                    file_type="generated",
                    file_path=str(path),
                    file_size=path.stat().st_size,
                    config=self.config,
                    user_id=session.user_id,
                    source="generated",
                    role="output",
                    task_uuid=str(task_uuid) if task_uuid else None,
                    storage_key=storage_key,
                )
        except Exception as exc:
            self.logger.warning(f"登记生成文件失败: {exc}")

    def get_available_workflows(self) -> Dict[str, str]:
        """获取所有可用的工作流"""
        return {
            TaskType.DEFAULT_CONVERSATION.value: "默认对话模式 - 与AI自由交流",
            TaskType.DOCUMENT_UNDERSTANDING.value: "文档理解模式 - 解析并理解文档内容",
            TaskType.DOCUMENT_EDITING.value: "文档编辑模式 - 按要求编辑Word文档",
            TaskType.ENTITY_EXTRACTION.value: "实体提取模式 - 从文档中提取数据填入模板",
            TaskType.TABLE_FILLING.value: "表格填表模式 - 从Excel筛选数据填入表格",
            TaskType.WORKFLOW_PIPELINE.value: "工作流编排模式 - 按节点顺序处理文档",
        }

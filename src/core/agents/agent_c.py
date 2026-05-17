"""
Agent_C: 数据库Agent（可选）
负责将JSON数据存入数据库
"""
from typing import Any, Dict, Optional

from config import SystemConfig, get_config
from core.orchestrator.task_spec import TaskSpec
from db.connection import health_check
from db.repository import save_extraction_from_agent_payload_safe

from .base_agent import BaseAgent, AgentResponse


class AgentC(BaseAgent):
    """
    Agent_C: 数据库存储

    能力：
    - 将JSON数据存入数据库
    - 支持自动建表
    - 推荐使用PostgreSQL
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        super().__init__(config)
        self.name = "Agent_C"
        self.agent_type = "database"

    def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
        """
        执行数据库存储任务
        """
        if not self.config.database.enabled:
            return AgentResponse(
                success=False,
                message="数据库功能未启用"
            )

        ok, msg = health_check(self.config)
        if not ok:
            return AgentResponse(
                success=False,
                message=f"数据库连接失败: {msg}"
            )

        valid, verr = self.validate_input(task_spec)
        if not valid:
            return AgentResponse(success=False, message=verr)

        try:
            return self._store_to_database(task_spec)
        except Exception as e:
            return AgentResponse(
                success=False,
                message=f"存储失败: {str(e)}"
            )

    def _store_to_database(self, task_spec: TaskSpec) -> AgentResponse:
        """写入 tasks + extraction_results（契约 v1）。"""
        ok, outcome, err = save_extraction_from_agent_payload_safe(
            task_spec.parameters,
            task_spec.task_type.value,
            task_spec.session_id,
            self.config,
        )
        if not ok or outcome is None:
            return AgentResponse(
                success=False,
                message=err or "入库失败",
                metadata={"error_code": "VALIDATION_ERROR" if "缺少" in (err or "") or "必须为" in (err or "") else "INTERNAL_ERROR"},
            )
        return AgentResponse(
            success=True,
            message="抽取结果已写入数据库",
            data={
                "task_id": outcome.task_id,
                "task_uuid": outcome.task_uuid,
                "extraction_id": outcome.extraction_id,
                "result_version": outcome.result_version,
            },
        )

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """验证输入"""
        data = task_spec.parameters.get("data")
        if not isinstance(data, dict):
            return False, "缺少 parameters.data 或类型不是对象"
        if "fields" not in data:
            return False, "data 中缺少契约字段 fields"
        return True, ""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return get_config().agent.get_prompt(self.agent_type)

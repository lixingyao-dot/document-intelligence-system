"""
ConversationAgent: 对话Agent
用于默认对话模式，直接与用户交流
"""
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentResponse
from core.llm import get_llm_service
from core.orchestrator.task_spec import TaskSpec
from config import get_config
from utils.logger import get_logger


class ConversationAgent(BaseAgent):
    """
    ConversationAgent: 对话Agent

    能力：
    - 直接与用户交流
    - 回答系统相关问题
    - 提供使用帮助和指南
    """

    def __init__(self, config=None):
        super().__init__(config)
        self.name = "ConversationAgent"
        self.agent_type = "conversation"
        self.logger = get_logger(__name__)
        self._llm = get_llm_service()

    def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
        """
        执行对话任务
        """
        try:
            return self._converse(task_spec)
        except Exception as e:
            return AgentResponse(
                success=False,
                message=f"对话失败: {str(e)}"
            )

    def _converse(self, task_spec: TaskSpec) -> AgentResponse:
        """
        处理对话
        """
        user_input = task_spec.instruction

        # 调用LLM
        llm_response = self._call_llm(user_input, task_spec.conversation_history or [])

        return AgentResponse(
            success=True,
            message=llm_response,
            data={"mode": "conversation"}
        )

    def _call_llm(self, user_input: str, conversation_history: List[Dict]) -> str:
        """
        调用LLM进行对话
        """
        if not self._llm.is_available():
            raise ValueError("LLM 服务不可用，请检查 API Key 配置")

        messages = [{"role": "system", "content": self.get_system_prompt()}]
        messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": user_input})

        return self._llm.chat(messages, strip_markdown_output=False)

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """验证输入"""
        if not task_spec.instruction:
            return False, "缺少对话内容"
        return True, ""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return get_config().agent.get_prompt(self.agent_type)

    def get_capabilities(self) -> Dict[str, Any]:
        """获取Agent能力"""
        return {
            "name": self.name,
            "type": "conversation",
            "description": "默认对话Agent，支持自由交流和系统帮助",
            "features": [
                "自由对话",
                "系统使用指南",
                "功能介绍",
                "模式推荐",
            ]
        }

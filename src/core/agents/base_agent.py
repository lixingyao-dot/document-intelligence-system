"""
Agent基类
定义所有Agent的通用接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass

from config import SystemConfig
from core.orchestrator.task_spec import TaskSpec


@dataclass
class AgentResponse:
    """Agent响应"""
    success: bool
    message: str
    data: Any = None
    metadata: Dict[str, Any] = None


class BaseAgent(ABC):
    """
    Agent基类
    所有Agent需继承此类并实现核心方法
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
        """
        执行Agent任务
        必须由子类实现

        Args:
            task_spec: 任务规格对象

        Returns:
            AgentResponse: 执行结果
        """
        pass

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """
        验证输入
        子类可重写自定义验证逻辑

        Returns:
            (是否有效, 错误信息)
        """
        return True, ""

    def get_system_prompt(self) -> str:
        """
        获取系统提示词
        子类可重写以提供自定义提示词
        """
        return ""

    def get_capabilities(self) -> Dict[str, Any]:
        """
        获取Agent能力描述
        """
        return {
            "name": self.name,
            "type": self.__class__.__bases__[0].__name__,
        }

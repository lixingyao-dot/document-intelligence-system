"""
Core module.
文档解析由各Agent自行处理（不依赖统一的解析器）
"""

from .orchestrator import WorkflowCoordinator, TaskSpec, TaskType, TaskExecutor
from .agents import BaseAgent, DocumentAgent, AgentB, AgentC, AgentD

__all__ = [
    'WorkflowCoordinator', 'TaskSpec', 'TaskType', 'TaskExecutor',
    'BaseAgent', 'DocumentAgent', 'AgentB', 'AgentC', 'AgentD'
]

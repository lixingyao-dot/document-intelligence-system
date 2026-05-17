"""
Service Layer - 服务层
提供统一的业务接口，供 CLI 和 Web API 调用
"""
from .document_service import (
    DocumentUnderstandingService,
    SessionManager,
    Session,
    ChatMessage,
    get_service
)

__all__ = [
    'DocumentUnderstandingService',
    'SessionManager',
    'Session',
    'ChatMessage',
    'get_service'
]

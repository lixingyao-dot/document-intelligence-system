"""
Service Layer - 服务层
统一接口，支持 CLI 和 Web API
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import uuid
import threading
import os

from config import SystemConfig, get_config
from utils.logger import get_logger


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = 0


@dataclass
class Session:
    """会话"""
    session_id: str
    agent_type: str
    agent: Any
    file_path: Optional[str] = None
    messages: List[ChatMessage] = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []


class SessionManager:
    """
    会话管理器
    管理 Agent 实例和会话状态
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.logger = get_logger(__name__)
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self.config = get_config()
    
    def create_session(self, agent_type: str = "agent_a", 
                       file_path: Optional[str] = None) -> str:
        """
        创建新会话
        
        Args:
            agent_type: Agent 类型
            file_path: 文档路径（可选）
            
        Returns:
            session_id: 会话 ID
        """
        session_id = str(uuid.uuid4())[:8]
        
        # 动态加载 Agent
        agent = self._load_agent(agent_type)
        if not agent:
            raise ValueError(f"无法加载 Agent: {agent_type}")
        
        # 设置文档
        if file_path:
            if hasattr(agent, 'set_document'):
                agent.set_document(file_path)
            elif hasattr(agent, 'current_file_path'):
                agent.current_file_path = file_path
        
        session = Session(
            session_id=session_id,
            agent_type=agent_type,
            agent=agent,
            file_path=file_path
        )
        
        with self._lock:
            self._sessions[session_id] = session
        
        self.logger.info(f"创建会话: {session_id} (Agent: {agent_type})")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        with self._lock:
            return self._sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self.logger.info(f"关闭会话: {session_id}")
                return True
            return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "agent_type": s.agent_type,
                    "file_path": s.file_path,
                    "message_count": len(s.messages)
                }
                for s in self._sessions.values()
            ]
    
    def _load_agent(self, agent_type: str):
        """动态加载 Agent"""
        import importlib
        
        agent_map = {
            "agent_a": "core.agents.agent_a.AgentA",
            "agent_b": "core.agents.agent_b.AgentB",
            "agent_c": "core.agents.agent_c.AgentC",
            "agent_d": "core.agents.agent_d.AgentD",
        }
        
        agent_config = agent_map.get(agent_type)
        if not agent_config:
            return None
        
        try:
            module_path, class_name = agent_config.rsplit(".", 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            return agent_class(self.config)
        except Exception as e:
            self.logger.error(f"加载 Agent 失败 {agent_type}: {e}")
            return None


class DocumentUnderstandingService:
    """
    文档理解服务
    统一的 Service 接口，供 CLI 和 Web API 调用
    """
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.logger = get_logger(__name__)
    
    def start_document_session(self, file_path: str, 
                                agent_type: str = "agent_a") -> Dict[str, Any]:
        """
        启动文档理解会话
        
        Args:
            file_path: 文档路径
            agent_type: Agent 类型
            
        Returns:
            session_info: 包含 session_id 和初始信息
        """
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"文件不存在: {file_path}"
            }
        
        try:
            session_id = self.session_manager.create_session(
                agent_type=agent_type,
                file_path=file_path
            )
            
            return {
                "success": True,
                "session_id": session_id,
                "message": f"文档已加载: {os.path.basename(file_path)}",
                "commands": ["/quit 退出", "/clear 清除历史", "/history 查看历史"]
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def chat(self, session_id: str, message: str) -> Dict[str, Any]:
        """
        发送消息
        
        Args:
            session_id: 会话 ID
            message: 用户消息
            
        Returns:
            response: Agent 响应
        """
        session = self.session_manager.get_session(session_id)
        if not session:
            return {
                "success": False,
                "error": "会话不存在"
            }
        
        # 处理特殊命令
        if message.lower() in ['/quit', 'quit', 'exit', '退出']:
            self.session_manager.close_session(session_id)
            return {
                "success": True,
                "done": True,
                "message": "会话已结束"
            }
        
        if message.lower() == '/clear':
            session.agent.clear_history()
            return {
                "success": True,
                "message": "[已清除对话历史]"
            }
        
        if message.lower() == '/history':
            history = session.agent.get_history()
            return {
                "success": True,
                "message": "历史记录",
                "history": history
            }
        
        # 调用 Agent
        try:
            response = session.agent.chat(message)
            
            # 保存消息
            session.messages.append(ChatMessage(role="user", content=message))
            session.messages.append(ChatMessage(role="assistant", content=response))
            
            return {
                "success": True,
                "message": response,
                "done": False
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        return self.session_manager.close_session(session_id)


# 全局实例
_service_instance: Optional[DocumentUnderstandingService] = None

def get_service() -> DocumentUnderstandingService:
    """获取服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = DocumentUnderstandingService()
    return _service_instance

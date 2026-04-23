# -*- coding: utf-8 -*-
"""
会话管理器 - 支持多轮对话上下文
"""
import uuid
import time
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class ChatMessage:
    """单条消息"""
    def __init__(self, role: str, content: str, message_id: str = None):
        self.role = role  # "user" or "assistant"
        self.content = content
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = time.time()

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
        }

class ChatSession:
    """会话对象"""
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.messages: List[ChatMessage] = []
        self.created_at = time.time()
        self.last_active = time.time()
        self.metadata: Dict = {}  # 存储额外信息如当前处理的文件ID等
        self.last_evaluation: Dict = {}  # 存储上次评估结果，用于反馈重新评估

    def add_message(self, role: str, content: str) -> ChatMessage:
        """添加消息"""
        msg = ChatMessage(role, content)
        self.messages.append(msg)
        self.last_active = time.time()
        return msg

    def get_history(self, limit: int = 10) -> List[Dict]:
        """获取最近的消息历史"""
        recent = self.messages[-limit:]
        return [m.to_dict() for m in recent]
    
    def get_messages(self) -> List[Dict]:
        """获取所有消息"""
        return [m.to_dict() for m in self.messages]

    def get_context_prompt(self, limit: int = 5) -> str:
        """生成上下文提示词"""
        history = self.get_history(limit)
        if not history:
            return ""
        
        context_lines = []
        for msg in history:
            role = "用户" if msg["role"] == "user" else "助手"
            context_lines.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_lines)

    def get_last_evaluation(self) -> Dict:
        """获取上次评估结果"""
        return self.last_evaluation

    def set_last_evaluation(self, evaluation: Dict):
        """设置上次评估结果"""
        self.last_evaluation = evaluation

    def is_expired(self, timeout_hours: int = 2) -> bool:
        """检查会话是否过期"""
        return (time.time() - self.last_active) > (timeout_hours * 3600)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

class SessionManager:
    """会话管理器单例"""
    _instance = None
    _lock = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.sessions: Dict[str, ChatSession] = {}
        self.cleanup_interval = 30  # 清理间隔（秒）
        self.timeout_hours = 2  # 会话超时时间（小时）
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动定时清理线程"""
        import threading
        
        def cleanup_loop():
            while True:
                try:
                    self._cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"会话清理出错: {e}")
                time.sleep(self.cleanup_interval)
        
        t = threading.Thread(target=cleanup_loop, daemon=True)
        t.start()

    def _cleanup_expired_sessions(self):
        """清理过期会话"""
        expired = [sid for sid, sess in self.sessions.items() if sess.is_expired(self.timeout_hours)]
        for sid in expired:
            logger.info(f"清理过期会话: {sid}")
            del self.sessions[sid]

    def create_session(self) -> ChatSession:
        """创建新会话"""
        session = ChatSession()
        self.sessions[session.session_id] = session
        logger.info(f"创建新会话: {session.session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """获取会话"""
        session = self.sessions.get(session_id)
        if session:
            session.last_active = time.time()
        return session

    def delete_session(self, session_id: str):
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"删除会话: {session_id}")

    def get_session_list(self) -> List[Dict]:
        """获取所有会话列表"""
        return [s.to_dict() for s in self.sessions.values()]

    def get_session_count(self) -> int:
        """获取会话数量"""
        return len(self.sessions)

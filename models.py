"""数据模型定义"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """单条对话消息"""

    id: Optional[int] = None
    session_id: str
    role: str  # 'user' | 'assistant' | 'system' | 'tool'
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: Optional[datetime] = None


class Session(BaseModel):
    """Session 元数据"""

    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ToolCall(BaseModel):
    """LLM 返回的工具调用请求"""

    id: str
    name: str
    arguments: dict


class LLMResponse(BaseModel):
    """LLM API 的解析后响应"""

    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    usage: Optional[dict] = None


class AgentResult(BaseModel):
    """Agent 单轮对话的最终结果"""

    reply: str
    tokens_used: int = 0
    duration: float = 0.0
    turns: int = 0

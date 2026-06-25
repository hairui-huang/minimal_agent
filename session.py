"""Session 管理 — SQLite 存储"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from config import config
from models import Message, Session

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（简单实现，每次新建连接）"""
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """初始化数据库表结构"""
    if db_path:
        config.db_path = db_path
    conn = _get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        logger.info("数据库初始化完成: %s", config.db_path)
    finally:
        conn.close()


def create_session(title: Optional[str] = None) -> str:
    """创建新 session，返回 session ID"""
    sid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, title or f"session-{sid}", now, now),
        )
        conn.commit()
        logger.info("新建 session: %s", sid)
        return sid
    finally:
        conn.close()


def get_session(session_id: str) -> list[Message]:
    """获取 session 的全部历史消息"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [
            Message(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                tool_call_id=r["tool_call_id"],
                tool_name=r["tool_name"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def add_message(
    session_id: str,
    role: str,
    content: str,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> None:
    """向 session 添加一条消息"""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, tool_call_id, tool_name),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_sessions() -> list[Session]:
    """列出所有 session"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [
            Session(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def session_exists(session_id: str) -> bool:
    """检查 session 是否存在"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    """删除 session 及其消息"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        logger.info("已删除 session: %s", session_id)
    finally:
        conn.close()

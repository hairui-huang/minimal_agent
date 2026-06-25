"""待办事项工具（SQLite 持久化，按 session 隔离）"""

import json
import sqlite3
from datetime import datetime

from tools.registry import register_tool

# 数据库路径（与 session 共用同一个 DB）
_DB_PATH = "agent.db"


def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    """确保 todos 表存在"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


# 启动时建表
_ensure_table()


@register_tool(
    name="todo",
    description="管理待办事项。支持添加(add)、列出(list)、完成(complete)操作。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete"],
                "description": "操作类型: add=添加, list=列出, complete=标记完成",
            },
            "content": {
                "type": "string",
                "description": "待办内容（add 时必填）",
            },
            "todo_id": {
                "type": "integer",
                "description": "待办 ID（complete 时必填）",
            },
        },
        "required": ["action"],
    },
)
def todo(action: str, content: str = None, todo_id: int = None, session_id: str = "default") -> str:
    """管理待办事项（按 session 隔离，持久化到 SQLite）"""

    if action == "add":
        if not content:
            return json.dumps({"error": "添加待办需要 content 参数"}, ensure_ascii=False)
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO todos (session_id, content, done) VALUES (?, ?, 0)",
                (session_id, content),
            )
            conn.commit()
            item = {"id": cur.lastrowid, "content": content, "done": False}
            return json.dumps(
                {"message": f"已添加待办 #{item['id']}: {content}", "todo": item},
                ensure_ascii=False,
            )
        finally:
            conn.close()

    if action == "list":
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT id, content, done, created_at FROM todos WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            todos = [{"id": r["id"], "content": r["content"], "done": bool(r["done"]), "created_at": r["created_at"]} for r in rows]
            if not todos:
                return json.dumps({"message": "待办列表为空", "todos": []}, ensure_ascii=False)
            return json.dumps(
                {"message": f"共 {len(todos)} 条待办", "todos": todos},
                ensure_ascii=False,
            )
        finally:
            conn.close()

    if action == "complete":
        if todo_id is None:
            return json.dumps({"error": "完成待办需要 todo_id 参数"}, ensure_ascii=False)
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id, content, done FROM todos WHERE id = ? AND session_id = ?",
                (todo_id, session_id),
            ).fetchone()
            if row is None:
                return json.dumps({"error": f"未找到待办 #{todo_id}"}, ensure_ascii=False)
            conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
            conn.commit()
            return json.dumps(
                {"message": f"待办 #{todo_id} 已完成", "todo": {"id": row["id"], "content": row["content"], "done": True}},
                ensure_ascii=False,
            )
        finally:
            conn.close()

    return json.dumps({"error": f"未知操作: {action}"}, ensure_ascii=False)

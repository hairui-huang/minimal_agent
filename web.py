"""FastAPI Web 后端 — 为前端提供 REST API"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from config import config
from session import (
    add_message,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_sessions,
    session_exists,
)

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/web.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ── Lifespan: 启动时初始化数据库 ──────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库初始化完成")
    yield


app = FastAPI(title="Minimal Agent Runtime", lifespan=lifespan)

# CORS — 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求/响应模型 ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ToolCallInfo(BaseModel):
    name: str
    arguments: dict
    result: str


class ChatResponse(BaseModel):
    reply: str
    tokens_used: int = 0
    duration: float = 0.0
    turns: int = 0
    tool_calls: list[ToolCallInfo] = []


class SessionCreateRequest(BaseModel):
    title: Optional[str] = None


# ── API 路由 ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """提供前端页面"""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(
        html_path,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": config.model}


@app.get("/api/sessions")
async def api_list_sessions():
    sessions = list_sessions()
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": str(s.created_at),
            "updated_at": str(s.updated_at),
        }
        for s in sessions
    ]


@app.post("/api/sessions")
async def api_create_session(req: SessionCreateRequest = None):
    title = req.title if req else None
    sid = create_session(title)
    return {"id": sid, "title": title or f"session-{sid}"}


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_session(session_id)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_call_id": m.tool_call_id,
            "tool_name": m.tool_name,
            "created_at": str(m.created_at) if m.created_at else None,
        }
        for m in messages
    ]


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    delete_session(session_id)
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    """发送消息给 Agent，返回回复"""
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        # 导入 agent（延迟导入，避免启动时加载 LLM）
        from agent import run_agent
        from session import get_session as _get_session

        # 记录调用前的消息数，用于提取本次工具调用
        before_count = len(_get_session(req.session_id))

        result = run_agent(req.message, req.session_id)

        # 提取本次对话中的工具调用（从 assistant 消息中解析 tool_calls 信息）
        after_messages = _get_session(req.session_id)
        tool_calls = []
        # 构建 assistant tool_calls 映射: name+arguments 按顺序
        pending_tool_calls: list[dict] = []
        for msg in after_messages[before_count:]:
            if msg.role == "assistant" and msg.content:
                # 尝试解析 assistant 消息中的 tool_calls 信息
                try:
                    parsed = json.loads(msg.content)
                    if "tool_calls" in parsed:
                        pending_tool_calls = parsed["tool_calls"]
                except (json.JSONDecodeError, TypeError):
                    pending_tool_calls = []
            elif msg.role == "tool" and msg.tool_name:
                # 匹配 pending_tool_calls 中的第一个
                args = {}
                if pending_tool_calls:
                    tc_info = pending_tool_calls.pop(0)
                    args = tc_info.get("arguments", {})
                tool_calls.append(ToolCallInfo(
                    name=msg.tool_name,
                    arguments=args,
                    result=msg.content or "",
                ))

        return ChatResponse(
            reply=result.reply,
            tokens_used=result.tokens_used,
            duration=round(result.duration, 2),
            turns=result.turns,
            tool_calls=tool_calls,
        )
    except Exception as e:
        logger.exception("Agent 执行异常")
        raise HTTPException(status_code=500, detail="Agent 执行出错，请稍后重试")


# ── 启动 ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    if not config.api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        print("  cp .env.example .env  # 然后编辑 .env 填入你的 API Key")
        exit(1)

    print("=" * 50)
    print("  Minimal Agent Runtime — Web UI")
    print(f"  http://localhost:8000")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)

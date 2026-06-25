"""Agent Loop 核心 — 协调 LLM、工具、Context"""

from __future__ import annotations

import json
import logging
import time

import tools as _  # 触发所有工具的 @register_tool 注册，不要删除
from config import config
from context import build_messages
from llm import call_llm
from models import AgentResult, ToolCall
from session import add_message, get_session
from tools.registry import registry

logger = logging.getLogger(__name__)


def run_agent(user_input: str, session_id: str) -> AgentResult:
    """
    运行 Agent Loop：接收用户输入 → 调 LLM → 可能多轮工具调用 → 返回最终答案。

    Args:
        user_input: 用户输入
        session_id: session ID

    Returns:
        AgentResult: 包含最终回复、token 使用量、耗时、轮次
    """
    start_time = time.time()
    total_tokens = 0
    turns = 0

    # 记录用户输入
    add_message(session_id, "user", user_input)

    # 加载历史并构建 messages
    history = get_session(session_id)
    messages = build_messages(history, user_input)

    # 获取工具 schema
    tools_schema = registry.get_tools_schema()

    while turns < config.max_turns:
        turns += 1
        logger.info("[session:%s] [turn:%d] 调用 LLM", session_id, turns)

        # 调用 LLM
        response = call_llm(messages, tools_schema if tools_schema else None)

        # 累计 token
        if response.usage:
            total_tokens += response.usage.get("total_tokens", 0)

        # 如果没有工具调用，返回最终答案
        if not response.tool_calls:
            reply = response.content or "(空回复)"
            # 记录 assistant 回复
            add_message(session_id, "assistant", reply)
            duration = time.time() - start_time
            logger.info("[session:%s] 完成 (耗时 %.1fs, tokens=%d, turns=%d)",
                        session_id, duration, total_tokens, turns)
            return AgentResult(
                reply=reply,
                tokens_used=total_tokens,
                duration=duration,
                turns=turns,
            )

        # 有工具调用 → 逐个执行
        # 先把 assistant 的 tool_calls 消息加入 messages
        assistant_msg: dict = {"role": "assistant", "content": response.content or ""}
        if response.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ]
        messages.append(assistant_msg)

        # 记录 assistant 消息，把 tool_calls 信息序列化到 content 中
        tool_calls_info = [
            {"name": tc.name, "arguments": tc.arguments}
            for tc in response.tool_calls
        ]
        assistant_content = json.dumps({
            "text": response.content or "",
            "tool_calls": tool_calls_info,
        }, ensure_ascii=False)
        add_message(session_id, "assistant", assistant_content)

        # 执行每个工具调用
        for tc in response.tool_calls:
            logger.info("[session:%s] [turn:%d] 执行工具: %s(%s)",
                        session_id, turns, tc.name, json.dumps(tc.arguments, ensure_ascii=False))

            result = registry.execute(tc.name, tc.arguments)

            logger.info("[session:%s] [turn:%d] 工具结果: %s",
                        session_id, turns, result[:200])

            # 将工具结果加入 messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

            # 记录工具结果到 session
            add_message(
                session_id, "tool", result,
                tool_call_id=tc.id, tool_name=tc.name,
            )

    # 超过轮次限制
    reply = "抱歉，我在多次尝试后未能完成任务。请尝试简化您的问题。"
    add_message(session_id, "assistant", reply)
    duration = time.time() - start_time
    logger.warning("[session:%s] 超过最大轮次限制 (%d)", session_id, config.max_turns)
    return AgentResult(
        reply=reply,
        tokens_used=total_tokens,
        duration=duration,
        turns=turns,
    )

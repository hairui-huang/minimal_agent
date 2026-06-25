"""Context 管理 — 构建消息列表、滑动窗口、摘要压缩"""

from __future__ import annotations

import json
import logging
from typing import Optional

from config import config
from models import Message

logger = logging.getLogger(__name__)


def build_messages(
    session_history: list[Message],
    user_input: str,
    system_prompt: Optional[str] = None,
) -> list[dict]:
    """
    构建发送给 LLM 的 messages 列表。

    结构: [system] + [压缩摘要(如有)] + [最近N轮历史] + [当前用户输入]

    Args:
        session_history: session 历史消息
        user_input: 当前用户输入
        system_prompt: 自定义 system prompt（默认用 config 中的）

    Returns:
        OpenAI 格式的 messages 列表
    """
    messages: list[dict] = []

    # 1. System prompt
    messages.append({
        "role": "system",
        "content": system_prompt or config.system_prompt,
    })

    # 2. 将历史消息转为 OpenAI 格式
    history_formatted = _format_history(session_history)

    # 3. 如果历史过长，进行压缩
    if len(history_formatted) > config.max_context_turns * 2:
        history_formatted = compress_history(history_formatted, config.max_context_turns)

    messages.extend(history_formatted)

    # 4. 当前用户输入
    messages.append({"role": "user", "content": user_input})

    return messages


def _format_history(history: list[Message]) -> list[dict]:
    """将 Message 对象列表转为 OpenAI messages 格式

    处理 assistant 消息中的 tool_calls 信息：
    - 保存时 tool_calls 被序列化到 content JSON 中
    - 加载时需要还原为 OpenAI 要求的 tool_calls 字段
    - 同时用后续 tool 消息的 tool_call_id 来匹配
    """
    formatted: list[dict] = []
    # 收集所有 tool 消息的 tool_call_id，用于匹配
    tool_call_ids = {msg.tool_call_id for msg in history if msg.role == "tool" and msg.tool_call_id}

    i = 0
    while i < len(history):
        msg = history[i]

        if msg.role == "user":
            formatted.append({"role": "user", "content": msg.content or ""})

        elif msg.role == "assistant":
            # 尝试解析 content 中的 tool_calls 信息
            content = msg.content or ""
            parsed_tool_calls = None

            if content:
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and "tool_calls" in data:
                        # 从 JSON 中还原 tool_calls
                        content = data.get("text", "")
                        parsed_tool_calls = data["tool_calls"]
                except (json.JSONDecodeError, TypeError):
                    pass  # 普通文本，不是 JSON

            # 检查后续消息是否有关联的 tool 消息
            if parsed_tool_calls and i + 1 < len(history) and history[i + 1].role == "tool":
                # 从后续 tool 消息获取 tool_call_id
                tool_ids = []
                j = i + 1
                while j < len(history) and history[j].role == "tool":
                    if history[j].tool_call_id:
                        tool_ids.append(history[j].tool_call_id)
                    j += 1

                # 构建 tool_calls（优先用 JSON 中保存的 id，其次用 tool 消息的 id）
                tool_calls = []
                for idx, tc_info in enumerate(parsed_tool_calls):
                    tc_id = (tc_info.get("id")
                             or (tool_ids[idx] if idx < len(tool_ids) else None)
                             or f"call_{idx}_{hash(tc_info.get('name', '')) % 10000:04d}")
                    tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc_info["name"],
                            "arguments": json.dumps(tc_info["arguments"], ensure_ascii=False),
                        },
                    })

                entry: dict = {"role": "assistant", "content": content, "tool_calls": tool_calls}
                formatted.append(entry)
            else:
                entry: dict = {"role": "assistant", "content": content}
                formatted.append(entry)

        elif msg.role == "tool":
            # 检查前面是否有带 tool_calls 的 assistant 消息
            has_preceding_tool_calls = (
                formatted
                and formatted[-1].get("role") == "assistant"
                and "tool_calls" in formatted[-1]
            )
            if has_preceding_tool_calls:
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                })
            else:
                logger.debug("跳过孤立的 tool 消息 (无 preceding tool_calls): %s", msg.tool_call_id)

        elif msg.role == "system":
            # 跳过，system prompt 由 build_messages 管理
            pass

        i += 1

    return formatted


def compress_history(messages: list[dict], max_turns: int = 20) -> list[dict]:
    """
    摘要压缩：对早期对话调用 LLM 生成摘要，保留最近 N 轮原文。

    流程:
    1. 取出前半部分（要压缩的早期消息）
    2. 调用 LLM 生成摘要
    3. 用 [system: 摘要内容] 替代早期消息
    4. 拼接最近 N 轮原文

    Args:
        messages: 原始消息列表（不含 system prompt）
        max_turns: 保留最近多少轮原文

    Returns:
        压缩后的消息列表：[摘要消息] + [最近N轮]
    """
    keep = max_turns * 2  # 每轮 = user + assistant/tool
    if len(messages) <= keep:
        return messages

    # 分割：早期（要压缩） + 最近（保留原文）
    early = messages[:-keep]
    recent = messages[-keep:]

    dropped = len(early)
    logger.info("Context 压缩: %d 条早期消息将生成摘要", dropped)

    # 对早期消息生成摘要
    summary = _generate_summary(early)

    # 返回：[摘要] + [最近N轮]
    return [
        {"role": "system", "content": f"以下是之前对话的摘要：\n{summary}"}
    ] + recent


def _generate_summary(messages: list[dict]) -> str:
    """
    调用 LLM 对早期对话生成摘要。

    Args:
        messages: 要压缩的消息列表

    Returns:
        摘要文本
    """
    from llm import call_llm  # 延迟导入避免循环依赖

    # 把消息格式化成可读文本，方便 LLM 理解
    conversation_text = _messages_to_text(messages)

    summary_prompt = [
        {
            "role": "system",
            "content": (
                "你是一个对话摘要助手。请用简洁的中文总结以下对话的要点。\n"
                "要求：\n"
                "1. 保留关键信息（用户名字、偏好、重要结论、待办事项等）\n"
                "2. 保留工具调用的结果（如天气、计算结果等）\n"
                "3. 控制在 3-5 句话以内\n"
                "4. 不要添加对话中没有的信息"
            ),
        },
        {"role": "user", "content": conversation_text},
    ]

    try:
        response = call_llm(summary_prompt)
        summary = response.content or "(摘要生成失败)"
        logger.info("摘要生成成功: %s...", summary[:100])
        return summary
    except Exception as e:
        logger.error("摘要生成失败: %s", e)
        # 降级：简单截取前几条消息
        fallback = []
        for msg in messages[:6]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            if content:
                fallback.append(f"[{role}] {content}")
        return "(摘要生成失败，以下是早期对话片段)\n" + "\n".join(fallback)


def _messages_to_text(messages: list[dict]) -> str:
    """将 messages 列表转为可读文本"""
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"用户: {content}")
        elif role == "assistant":
            lines.append(f"助手: {content}")
        elif role == "tool":
            lines.append(f"工具结果: {content[:200]}")
    return "\n".join(lines)

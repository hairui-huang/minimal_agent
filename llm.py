"""LLM API 封装 — 调用 DeepSeek（OpenAI 兼容）"""

from __future__ import annotations

import json
import logging
import time

from openai import OpenAI

from config import config
from models import LLMResponse, ToolCall

logger = logging.getLogger(__name__)

# 模块级单例客户端，避免每次调用都创建新连接
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """获取 OpenAI 客户端单例（指向 DeepSeek）"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.api_key, base_url=config.api_base)
    return _client


def call_llm(messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
    """
    调用 LLM API，支持重试。

    Args:
        messages: OpenAI 格式的消息列表
        tools: function calling 的 tools schema（可选）

    Returns:
        LLMResponse: 解析后的响应
    """
    client = _get_client()
    last_error = None

    for attempt in range(config.max_retries + 1):
        try:
            kwargs = {
                "model": config.model,
                "messages": messages,
                "temperature": 0.7,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            # 解析工具调用
            tool_calls = None
            if message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(
                        ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                    )

            # 解析 usage
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                usage=usage,
            )

        except Exception as e:
            last_error = e
            if attempt < config.max_retries:
                wait = 2 ** attempt
                logger.warning("LLM 调用失败 (尝试 %d/%d): %s，%ds 后重试",
                               attempt + 1, config.max_retries, e, wait)
                time.sleep(wait)
            else:
                logger.error("LLM 调用最终失败: %s", e)

    raise RuntimeError(f"LLM 调用失败（重试 {config.max_retries} 次后）: {last_error}")

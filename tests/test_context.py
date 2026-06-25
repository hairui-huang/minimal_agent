"""Context 管理测试"""

import os
import pytest
from unittest.mock import patch, MagicMock

from config import config
from context import build_messages, compress_history, _generate_summary
from models import Message


def _make_history(n: int) -> list[Message]:
    """生成 n 轮对话历史"""
    messages = []
    for i in range(n):
        messages.append(Message(
            session_id="test",
            role="user",
            content=f"用户消息 {i}",
        ))
        messages.append(Message(
            session_id="test",
            role="assistant",
            content=f"助手回复 {i}",
        ))
    return messages


class TestBuildMessages:
    """消息构建测试"""

    def test_basic_structure(self):
        """基本消息结构：system + user"""
        messages = build_messages([], "你好")
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "你好"

    def test_with_history(self):
        """包含历史消息"""
        history = _make_history(2)
        messages = build_messages(history, "新问题")
        # system + 4条历史 + 1条用户输入
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "新问题"

    def test_custom_system_prompt(self):
        """自定义 system prompt"""
        messages = build_messages([], "你好", system_prompt="你是猫娘")
        assert messages[0]["content"] == "你是猫娘"


class TestCompressHistory:
    """Context 压缩测试（使用 mock 避免真实 LLM 调用）"""

    def test_no_compression_needed(self):
        """消息数量未超限时不做压缩"""
        messages = [{"role": "user", "content": "hi"}] * 10
        result = compress_history(messages, max_turns=20)
        assert len(result) == 10

    @patch("context._generate_summary")
    def test_compression_with_summary(self, mock_summary):
        """超过限制时调用 LLM 生成摘要"""
        mock_summary.return_value = "用户问了关于 Python 的问题"

        messages = [{"role": "user", "content": f"msg {i}"} for i in range(100)]
        result = compress_history(messages, max_turns=10)

        # 第一条应该是摘要（system role）
        assert result[0]["role"] == "system"
        assert "摘要" in result[0]["content"]
        assert "用户问了关于 Python 的问题" in result[0]["content"]

        # 后面保留最近 20 条
        assert len(result) == 21  # 1 摘要 + 20 历史

        # 保留的是最后 20 条
        assert result[1]["content"] == "msg 80"
        assert result[-1]["content"] == "msg 99"

        # 验证调用了摘要生成
        mock_summary.assert_called_once()

    @patch("llm.call_llm")
    def test_summary_generation_calls_llm(self, mock_call_llm):
        """摘要生成应调用 LLM"""
        mock_response = MagicMock()
        mock_response.content = "这是摘要"
        mock_call_llm.return_value = mock_response

        early_messages = [
            {"role": "user", "content": "我叫小明"},
            {"role": "assistant", "content": "好的，记住你了"},
        ]
        result = _generate_summary(early_messages)

        assert result == "这是摘要"
        mock_call_llm.assert_called_once()

    @patch("llm.call_llm")
    def test_summary_fallback_on_error(self, mock_call_llm):
        """LLM 调用失败时降级为简单截取"""
        mock_call_llm.side_effect = RuntimeError("API 失败")

        early_messages = [
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
            {"role": "user", "content": "消息2"},
            {"role": "assistant", "content": "回复2"},
        ]
        result = _generate_summary(early_messages)

        assert "摘要生成失败" in result
        assert "消息1" in result  # 降级内容包含早期消息

    def test_exact_limit_no_compression(self):
        """恰好等于限制时不压缩"""
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(40)]
        result = compress_history(messages, max_turns=20)
        assert len(result) == 40

    @patch("context._generate_summary")
    def test_compression_preserves_system_prompt(self, mock_summary):
        """压缩后摘要以 system role 出现，不会被过滤"""
        mock_summary.return_value = "摘要内容"

        messages = [{"role": "user", "content": f"msg {i}"} for i in range(60)]
        result = compress_history(messages, max_turns=10)

        # 第一条是摘要，role 是 system
        assert result[0]["role"] == "system"
        # 后面都是普通消息
        for msg in result[1:]:
            assert msg["role"] != "system" or "摘要" not in msg.get("content", "")

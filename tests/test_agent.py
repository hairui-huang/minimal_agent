"""Agent Loop 集成测试

注意：以下测试需要有效的 DEEPSEEK_API_KEY。
没有 API Key 时，这些测试会自动跳过。
"""

import os
import pytest

# 检查是否有 API Key
HAS_API_KEY = bool(os.getenv("DEEPSEEK_API_KEY"))

pytestmark = pytest.mark.skipif(
    not HAS_API_KEY,
    reason="需要 DEEPSEEK_API_KEY 环境变量",
)


@pytest.fixture(autouse=True)
def setup_env(tmp_path):
    """每个测试使用独立数据库"""
    import session as sess
    db_path = str(tmp_path / "test_agent.db")
    sess.init_db(db_path)
    yield


class TestAgentConversation:
    """Agent 对话测试"""

    def test_simple_chat(self):
        """纯对话（不调工具）应直接返回答案"""
        from agent import run_agent
        from session import create_session

        sid = create_session()
        result = run_agent("1+1等于几？请直接回答数字", sid)
        assert "2" in result.reply
        assert result.duration > 0

    def test_tool_call_calculator(self):
        """应调用计算器工具"""
        from agent import run_agent
        from session import create_session

        sid = create_session()
        result = run_agent("请计算 123 * 456", sid)
        assert "56088" in result.reply.replace(",", "")

    def test_tool_call_weather(self):
        """应调用天气工具"""
        from agent import run_agent
        from session import create_session

        sid = create_session()
        result = run_agent("今天北京天气怎么样？", sid)
        # mock 天气应该返回包含北京的信息
        assert "北京" in result.reply or "晴" in result.reply

    def test_multi_tool_chain(self):
        """多工具调用链：查天气 → 记待办"""
        from agent import run_agent
        from session import create_session

        sid = create_session()
        result = run_agent("帮我查一下北京天气，然后把结果记到待办里", sid)
        assert result.turns >= 1
        assert len(result.reply) > 0

    def test_session_continuity(self):
        """同一 session 应记住之前的对话"""
        from agent import run_agent
        from session import create_session

        sid = create_session()
        run_agent("我的名字叫小明", sid)
        result = run_agent("我叫什么名字？", sid)
        assert "小明" in result.reply

    def test_max_turns_limit(self):
        """超过轮次限制应强制返回"""
        from agent import run_agent
        from session import create_session
        from config import config

        # 临时降低轮次限制
        original = config.max_turns
        config.max_turns = 1
        try:
            sid = create_session()
            result = run_agent("帮我查北京天气然后查上海天气然后查深圳天气然后都记到待办", sid)
            # 应该返回（可能不完整，但不会无限循环）
            assert len(result.reply) > 0
        finally:
            config.max_turns = original


class TestSessionIsolation:
    """Session 隔离测试"""

    def test_two_sessions_independent(self):
        """两个 session 互不影响"""
        from agent import run_agent
        from session import create_session, get_session

        sid1 = create_session("session 1")
        sid2 = create_session("session 2")

        run_agent("我的爱好是编程", sid1)
        run_agent("我的爱好是游泳", sid2)

        history1 = get_session(sid1)
        history2 = get_session(sid2)

        # session 1 应该包含"编程"
        contents1 = " ".join(m.content or "" for m in history1)
        assert "编程" in contents1

        # session 2 应该包含"游泳"
        contents2 = " ".join(m.content or "" for m in history2)
        assert "游泳" in contents2

        # session 1 不应该包含"游泳"
        assert "游泳" not in contents1

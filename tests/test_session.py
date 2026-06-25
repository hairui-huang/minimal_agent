"""Session 管理测试"""

import os
import pytest

import session as sess


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """每个测试使用独立的临时数据库"""
    db_path = str(tmp_path / "test.db")
    sess.init_db(db_path)
    yield
    # tmp_path 自动清理


class TestSessionCRUD:
    """Session CRUD 测试"""

    def test_create_session(self):
        sid = sess.create_session("测试 session")
        assert sid is not None
        assert len(sid) == 8

    def test_list_sessions(self):
        sess.create_session("session 1")
        sess.create_session("session 2")
        sessions = sess.list_sessions()
        assert len(sessions) == 2

    def test_session_exists(self):
        sid = sess.create_session()
        assert sess.session_exists(sid) is True
        assert sess.session_exists("nonexistent") is False

    def test_delete_session(self):
        sid = sess.create_session()
        assert sess.session_exists(sid) is True
        sess.delete_session(sid)
        assert sess.session_exists(sid) is False


class TestMessageOperations:
    """消息操作测试"""

    def test_add_and_get_messages(self):
        sid = sess.create_session()
        sess.add_message(sid, "user", "你好")
        sess.add_message(sid, "assistant", "你好！有什么可以帮你的？")

        history = sess.get_session(sid)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "你好"
        assert history[1].role == "assistant"

    def test_tool_message(self):
        sid = sess.create_session()
        sess.add_message(sid, "user", "查天气")
        sess.add_message(sid, "assistant", "(工具调用)")
        sess.add_message(
            sid, "tool", '{"city": "北京", "weather": "晴"}',
            tool_call_id="call_123", tool_name="get_weather",
        )
        sess.add_message(sid, "assistant", "北京今天天气晴朗。")

        history = sess.get_session(sid)
        assert len(history) == 4

        tool_msg = history[2]
        assert tool_msg.role == "tool"
        assert tool_msg.tool_name == "get_weather"
        assert tool_msg.tool_call_id == "call_123"

    def test_session_isolation(self):
        """两个 session 的消息互不影响"""
        sid1 = sess.create_session("session 1")
        sid2 = sess.create_session("session 2")

        sess.add_message(sid1, "user", "session 1 的消息")
        sess.add_message(sid2, "user", "session 2 的消息")

        history1 = sess.get_session(sid1)
        history2 = sess.get_session(sid2)

        assert len(history1) == 1
        assert len(history2) == 1
        assert history1[0].content == "session 1 的消息"
        assert history2[0].content == "session 2 的消息"

    def test_empty_session_history(self):
        sid = sess.create_session()
        history = sess.get_session(sid)
        assert history == []

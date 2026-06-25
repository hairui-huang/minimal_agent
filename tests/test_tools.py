"""工具系统测试"""

import pytest

# 确保工具注册
import tools  # noqa: F401
from tools.registry import registry


class TestToolRegistry:
    """工具注册表测试"""

    def test_tools_registered(self):
        """所有工具应已注册"""
        tool_names = registry.list_tools()
        assert "calculator" in tool_names
        assert "search" in tool_names
        assert "todo" in tool_names
        assert "get_weather" in tool_names

    def test_tools_schema_format(self):
        """tools schema 应符合 OpenAI function calling 格式"""
        schema = registry.get_tools_schema()
        assert len(schema) >= 4
        for tool in schema:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_execute_unknown_tool(self):
        """执行未知工具应返回错误信息"""
        result = registry.execute("nonexistent", {})
        assert "未知工具" in result


class TestCalculator:
    """计算器工具测试"""

    def test_basic_addition(self):
        result = registry.execute("calculator", {"expression": "2 + 3"})
        assert result == "5"

    def test_complex_expression(self):
        result = registry.execute("calculator", {"expression": "2 + 3 * 4"})
        assert result == "14"

    def test_division(self):
        result = registry.execute("calculator", {"expression": "10 / 3"})
        assert "3.333" in result

    def test_division_by_zero(self):
        result = registry.execute("calculator", {"expression": "1 / 0"})
        assert "错误" in result

    def test_invalid_expression(self):
        result = registry.execute("calculator", {"expression": "hello"})
        assert "错误" in result

    def test_power(self):
        result = registry.execute("calculator", {"expression": "2 ** 10"})
        assert result == "1024"


class TestSearch:
    """搜索工具测试"""

    def test_search_known_keyword(self):
        result = registry.execute("search", {"query": "python"})
        assert "Python" in result

    def test_search_unknown_keyword(self):
        result = registry.execute("search", {"query": "xyzabc123"})
        assert "未找到" in result


class TestTodo:
    """待办工具测试"""

    def test_add_todo(self):
        result = registry.execute("todo", {"action": "add", "content": "买菜"})
        assert "已添加" in result

    def test_list_todos(self):
        result = registry.execute("todo", {"action": "list"})
        assert "待办" in result

    def test_complete_todo(self):
        result = registry.execute("todo", {"action": "complete", "todo_id": 1})
        assert "已完成" in result

    def test_add_without_content(self):
        result = registry.execute("todo", {"action": "add"})
        assert "error" in result.lower() or "需要" in result

    def test_complete_nonexistent(self):
        result = registry.execute("todo", {"action": "complete", "todo_id": 99999})
        assert "未找到" in result


class TestWeather:
    """天气工具测试"""

    def test_known_city(self):
        result = registry.execute("get_weather", {"city": "北京"})
        assert "北京" in result
        assert "°C" in result

    def test_unknown_city(self):
        result = registry.execute("get_weather", {"city": "火星"})
        assert "火星" in result

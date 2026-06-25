"""搜索工具 (Mock 实现)"""

from tools.registry import register_tool

# Mock 搜索数据
_MOCK_DATA = {
    "python": "Python 是一种高级编程语言，由 Guido van Rossum 于 1991 年首次发布。",
    "agent": "AI Agent 是能够自主感知环境并采取行动的人工智能系统。",
    "deepseek": "DeepSeek 是一家中国 AI 公司，开发了 DeepSeek 系列大语言模型。",
    "天气": "天气是指大气层中短期的气象状态变化。",
}


@register_tool(
    name="search",
    description="搜索网络信息（当前为 mock 实现，返回预设结果）",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            }
        },
        "required": ["query"],
    },
)
def search(query: str) -> str:
    """返回 mock 搜索结果"""
    query_lower = query.lower()
    for key, value in _MOCK_DATA.items():
        if key in query_lower:
            return f"搜索结果: {value}"
    return f"搜索结果: 未找到与 '{query}' 相关的信息。"

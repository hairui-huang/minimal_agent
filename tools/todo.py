"""待办事项 + 天气工具"""

import json
from datetime import datetime

from tools.registry import register_tool

# 内存中的待办列表（按 session 隔离由 agent 层处理，这里简单用全局列表）
_todos: list[dict] = []
_next_id = 1

# Mock 天气数据
_MOCK_WEATHER = {
    "北京": "晴，25°C，湿度 40%",
    "上海": "多云，28°C，湿度 65%",
    "深圳": "阵雨，30°C，湿度 80%",
    "杭州": "阴，22°C，湿度 55%",
    "成都": "小雨，20°C，湿度 70%",
    "default": "晴转多云，24°C，湿度 50%",
}


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
def todo(action: str, content: str = None, todo_id: int = None) -> str:
    """管理待办事项"""
    global _next_id

    if action == "add":
        if not content:
            return json.dumps({"error": "添加待办需要 content 参数"}, ensure_ascii=False)
        item = {
            "id": _next_id,
            "content": content,
            "done": False,
            "created_at": datetime.now().isoformat(),
        }
        _todos.append(item)
        _next_id += 1
        return json.dumps(
            {"message": f"已添加待办 #{item['id']}: {content}", "todo": item},
            ensure_ascii=False,
        )

    if action == "list":
        if not _todos:
            return json.dumps({"message": "待办列表为空", "todos": []}, ensure_ascii=False)
        return json.dumps(
            {"message": f"共 {len(_todos)} 条待办", "todos": _todos},
            ensure_ascii=False,
        )

    if action == "complete":
        if todo_id is None:
            return json.dumps({"error": "完成待办需要 todo_id 参数"}, ensure_ascii=False)
        for item in _todos:
            if item["id"] == todo_id:
                item["done"] = True
                return json.dumps(
                    {"message": f"待办 #{todo_id} 已完成", "todo": item},
                    ensure_ascii=False,
                )
        return json.dumps({"error": f"未找到待办 #{todo_id}"}, ensure_ascii=False)

    return json.dumps({"error": f"未知操作: {action}"}, ensure_ascii=False)


@register_tool(
    name="get_weather",
    description="查询指定城市的天气信息（mock 实现）",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 北京、上海、深圳",
            }
        },
        "required": ["city"],
    },
)
def get_weather(city: str) -> str:
    """返回 mock 天气信息，支持模糊匹配（如"北京市"匹配"北京"）"""
    # 先精确匹配，再模糊匹配
    weather = _MOCK_WEATHER.get(city)
    if weather is None:
        for key, value in _MOCK_WEATHER.items():
            if key != "default" and (key in city or city in key):
                weather = value
                break
    if weather is None:
        weather = _MOCK_WEATHER["default"]
    return json.dumps(
        {"city": city, "weather": weather, "source": "mock"},
        ensure_ascii=False,
    )

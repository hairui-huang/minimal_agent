"""天气查询工具（mock 实现）"""

import json

from tools.registry import register_tool

# Mock 天气数据
_MOCK_WEATHER = {
    "北京": "晴，25°C，湿度 40%",
    "上海": "多云，28°C，湿度 65%",
    "深圳": "阵雨，30°C，湿度 80%",
    "杭州": "阴，22°C，湿度 55%",
    "成都": "小雨，20°C，湿度 70%",
    "贵阳": "晴转多云，24°C，湿度 50%",
    "default": "晴转多云，24°C，湿度 50%",
}


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

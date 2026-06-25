"""工具注册机制

使用装饰器 @register_tool 注册工具函数，自动生成 OpenAI function calling 格式的 schema。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """已注册工具的元信息"""

    name: str
    description: str
    parameters: dict
    func: Callable


class ToolRegistry:
    """全局工具注册表"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolInfo] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
    ) -> Callable:
        """装饰器：注册一个工具函数"""

        def decorator(func: Callable) -> Callable:
            self._tools[name] = ToolInfo(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
            )
            logger.info("工具已注册: %s", name)
            return func

        return decorator

    def get_tools_schema(self) -> list[dict]:
        """返回 OpenAI function calling 格式的 tools 列表"""
        return [
            {
                "type": "function",
                "function": {
                    "name": info.name,
                    "description": info.description,
                    "parameters": info.parameters,
                },
            }
            for info in self._tools.values()
        ]

    def execute(self, tool_name: str, arguments: dict, context: dict | None = None) -> str:
        """执行指定工具，返回结果字符串。异常时返回错误信息。

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 额外上下文（如 session_id），会作为 kwargs 传给工具函数
        """
        info = self._tools.get(tool_name)
        if info is None:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
        try:
            kwargs = {**arguments}
            if context:
                kwargs.update(context)
            result = info.func(**kwargs)
            return str(result)
        except Exception as e:
            logger.exception("工具 %s 执行异常", tool_name)
            return json.dumps({"error": f"工具执行异常: {e}"}, ensure_ascii=False)

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名称"""
        return list(self._tools.keys())


# 全局单例
registry = ToolRegistry()

# 便捷别名
register_tool = registry.register

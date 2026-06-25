import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """全局配置，从环境变量读取"""

    # LLM 配置
    api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    api_base: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    )
    model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )

    # Agent 配置
    max_turns: int = 10  # 单次对话最大工具调用轮次
    max_context_turns: int = 20  # context 保留的最大轮次
    max_retries: int = 2  # LLM 调用重试次数

    # Session 配置
    db_path: str = "agent.db"

    # System Prompt
    system_prompt: str = (
        "你是一个有用的 AI 助手。你可以使用工具来帮助用户完成任务。\n"
        "当需要使用工具时，请调用相应的函数。\n"
        "当不需要使用工具时，直接回复用户。"
    )


# 全局单例
config = Config()

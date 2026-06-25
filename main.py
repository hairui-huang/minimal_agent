"""CLI 入口 — 用户交互循环"""

from __future__ import annotations  # 兼容 Python 3.9+

import logging
import os
import sys

from config import config
from session import (
    create_session,
    delete_session,
    init_db,
    list_sessions,
    session_exists,
)

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/agent.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def print_welcome() -> None:
    """打印欢迎信息"""
    print("=" * 50)
    print("  Minimal Agent Runtime")
    print("  DeepSeek + Tool Calling")
    print("=" * 50)
    print()
    print("命令:")
    print("  /new          - 新建 session")
    print("  /list         - 列出所有 session")
    print("  /switch <id>  - 切换 session")
    print("  /history      - 查看当前 session 历史")
    print("  /delete <id>  - 删除 session")
    print("  /quit         - 退出")
    print("  其他输入      - 与 Agent 对话")
    print()


def handle_command(cmd: str, current_session: str) -> str | None:
    """
    处理命令，返回新的 current_session（如果切换了的话）。
    返回 None 表示退出。
    """
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/quit":
        print("再见！")
        return None

    if command == "/new":
        sid = create_session()
        print(f"✓ 已创建新 session: {sid}")
        return sid

    if command == "/list":
        sessions = list_sessions()
        if not sessions:
            print("暂无 session")
        else:
            print(f"{'ID':<10} {'标题':<25} {'最后更新'}")
            print("-" * 60)
            for s in sessions:
                marker = " ← 当前" if s.id == current_session else ""
                print(f"{s.id:<10} {s.title:<25} {s.updated_at}{marker}")
        return current_session

    if command == "/switch":
        if not arg:
            print("用法: /switch <session_id>")
            return current_session
        if session_exists(arg):
            print(f"✓ 已切换到 session: {arg}")
            return arg
        print(f"✗ session 不存在: {arg}")
        return current_session

    if command == "/history":
        from session import get_session
        history = get_session(current_session)
        if not history:
            print("当前 session 暂无历史")
        else:
            for msg in history:
                role_label = {"user": "你", "assistant": "Agent", "tool": "工具"}.get(msg.role, msg.role)
                content = msg.content or ""
                if msg.tool_name:
                    content = f"[{msg.tool_name}] {content}"
                print(f"  {role_label}: {content[:200]}")
        return current_session

    if command == "/delete":
        if not arg:
            print("用法: /delete <session_id>")
            return current_session
        delete_session(arg)
        print(f"✓ 已删除 session: {arg}")
        if arg == current_session:
            sid = create_session()
            print(f"✓ 已自动创建新 session: {sid}")
            return sid
        return current_session

    print(f"未知命令: {command}")
    return current_session


def main() -> None:
    """主入口"""
    # 检查 API Key
    if not config.api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        print("  cp .env.example .env  # 然后编辑 .env 填入你的 API Key")
        sys.exit(1)

    # 初始化数据库
    init_db()

    print_welcome()

    # 自动创建第一个 session
    current_session = create_session()
    print(f"当前 session: {current_session}")
    print()

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # 命令处理
        if user_input.startswith("/"):
            result = handle_command(user_input, current_session)
            if result is None:
                break
            current_session = result
            print()
            continue

        # 调用 Agent
        try:
            from agent import run_agent

            print("Agent 正在思考...", end="", flush=True)
            agent_result = run_agent(user_input, current_session)
            print("\r", end="")  # 清除 "正在思考..."

            print(f"Agent: {agent_result.reply}")
            print(f"  [tokens={agent_result.tokens_used}, "
                  f"耗时={agent_result.duration:.1f}s, "
                  f"轮次={agent_result.turns}]")
        except Exception as e:
            print(f"\n错误: {e}")
            logger.exception("Agent 执行异常")

        print()


if __name__ == "__main__":
    main()

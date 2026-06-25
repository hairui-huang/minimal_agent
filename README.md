# Minimal Agent Runtime

从零实现的最小可用 Agent Runtime。不依赖 LangGraph、OpenHands 等框架，核心 Agent Loop、工具注册、Session 管理、Context 管理全部自行实现。

基于 DeepSeek API（OpenAI 兼容），支持 function calling，LLM 自主决策工具调用。

## Features

- **Agent Loop** — 接收输入 → 调 LLM → 判断是否调工具 → 执行 → 循环或返回
- **工具注册** — 装饰器 `@register_tool` 注册，自动生成 OpenAI function calling schema
- **内置工具** — 计算器（AST 安全求值）、搜索（mock）、待办管理、天气查询（mock）
- **Session 隔离** — SQLite 存储，多 session 互不影响，随时切换
- **Context 管理** — 滑动窗口 + 基础压缩，防止 token 超限
- **异常处理** — LLM 调用重试、工具异常捕获、轮次限制
- **执行日志** — 全链路 trace，记录每轮 LLM 调用、工具执行、token 用量

## Quick Start

### Prerequisites

- Python 3.9+
- DeepSeek API Key

### Install

```bash
git clone <repo-url>
cd minimal-agent-runtime
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### Run

```bash
python main.py
```

启动后进入交互式 CLI，直接输入文字与 Agent 对话。

### CLI Commands

| Command | Description |
|---------|-------------|
| `/new` | 新建 session |
| `/list` | 列出所有 session |
| `/switch <id>` | 切换到指定 session |
| `/history` | 查看当前 session 历史 |
| `/delete <id>` | 删除 session |
| `/quit` | 退出程序 |

其他任何输入都会作为消息发送给 Agent。

## How It Works

### Agent Loop

```
用户输入
    │
    ▼
加载 session history (SQLite)
    │
    ▼
构建 messages = [system prompt] + [历史] + [用户输入]
    │
    ▼
调用 DeepSeek API (带 tools schema)
    │
    ▼
解析响应 ─────────────────────────┐
    │                              │
    ├─ 有 tool_call                │
    │   → 执行工具                  │
    │   → 结果追加到 messages       │
    │   → 回到"调用 LLM"           │
    │                              │
    └─ 无 tool_call                │
        → 保存回复到 session ──────┘
        → 返回给用户
```

每次循环都会检查轮次限制（默认 10 轮），超过则强制返回。

### Tool Registration

使用装饰器注册工具，LLM 根据 schema 自主决策调用：

```python
from tools.registry import register_tool

@register_tool(
    name="calculator",
    description="执行数学计算",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式"}
        },
        "required": ["expression"]
    }
)
def calculator(expression: str) -> str:
    # AST 安全求值，不使用 eval
    ...
```

新增工具只需：写一个函数 + 加 `@register_tool` 装饰器，无需修改其他代码。

### Context Management

每次对话时构建发送给 LLM 的消息列表：

```
[System Prompt]          ← 固定，定义 Agent 角色
[最近 N 轮对话]          ← 滑动窗口，默认 N=20
[当前用户输入]           ← 本次输入
```

当历史超过 `max_context_turns * 2` 条时，自动截断早期消息。

### Session Isolation

每个 session 是独立的对话空间，存储在 SQLite 中：

```bash
# 窗口 1：查天气记待办
你: 帮我查北京天气，记到待办里
Agent: 北京今天晴，25°C。已添加待办。

# 窗口 2：写周报记待办（互不影响）
你: 帮我写本周周报
Agent: 本周完成了...
```

切换 session 使用 `/switch <id>`，或用 `/list` 查看所有 session。

## Project Structure

```
minimal-agent-runtime/
├── main.py              # CLI 入口，交互循环
├── agent.py             # Agent Loop 核心逻辑
├── llm.py               # DeepSeek API 封装 + 重试
├── context.py           # 消息构建 + 滑动窗口压缩
├── session.py           # SQLite Session CRUD
├── models.py            # Pydantic 数据模型
├── config.py            # 全局配置
├── tools/
│   ├── registry.py      # 工具注册表 + 装饰器
│   ├── calculator.py    # 计算器（AST 安全求值）
│   ├── search.py        # 搜索（mock）
│   └── todo.py          # 待办 + 天气（mock）
├── tests/
│   ├── test_agent.py    # Agent Loop 集成测试
│   ├── test_tools.py    # 工具单元测试
│   ├── test_session.py  # Session 测试
│   └── test_context.py  # Context 测试
└── logs/                # 运行日志
```

## Testing

不需要 API Key 的测试（工具、Session、Context）：

```bash
pytest tests/test_tools.py tests/test_session.py tests/test_context.py -v
```

全部测试（需要 `DEEPSEEK_API_KEY` 环境变量）：

```bash
pytest tests/ -v
```

39 个测试用例覆盖：

| Module | Tests | Coverage |
|--------|-------|----------|
| Tools | 18 | 注册、计算器、搜索、待办、天气 |
| Session | 8 | CRUD、隔离、消息操作 |
| Context | 6 | 构建、压缩、滑动窗口 |
| Agent | 7 | 对话、工具调用、多轮链、session 连续性、轮次限制、session 隔离 |

## Logging

运行日志自动保存到 `logs/agent.log`，记录每轮的 LLM 调用、工具执行和 token 用量：

```
[2026-06-24 22:50:01] INFO [session:abc123] [turn:1] 调用 LLM
[2026-06-24 22:50:02] INFO [session:abc123] [turn:1] 执行工具: get_weather({"city": "北京"})
[2026-06-24 22:50:02] INFO [session:abc123] [turn:1] 工具结果: {"city": "北京", ...}
[2026-06-24 22:50:03] INFO [session:abc123] 完成 (耗时 2.1s, tokens=350, turns=2)
```

## What's Missing

这个 Agent Runtime 实现了核心循环，但离生产可用还差：

| Feature | Priority | Description |
|---------|----------|-------------|
| 流式输出 | High | 逐字输出，改善用户体验 |
| 向量记忆 | High | 长期记忆，跨 session 语义召回 |
| 并行工具调用 | Medium | 多个工具同时执行 |
| 智能压缩 | Medium | LLM 摘要替代简单截断 |
| 状态机 | Medium | 复杂任务的状态管理 |
| 权限控制 | Medium | 工具调用确认机制 |
| 多模态 | Low | 图片、文件处理 |
| 可观测性 | Low | Tracing、监控仪表盘 |

# Minimal Agent Runtime 设计文档

## 概述

从零实现一个最小可用 Agent Runtime，支持基本的 Agent Loop、工具调用、Session 管理和 Context 管理。

## 技术选型

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 语言 | Python | 生态成熟，LLM SDK 完善 |
| LLM API | DeepSeek（OpenAI 兼容） | 用户指定 |
| 架构 | 分层单体（同步） | 简单清晰，面试友好 |
| 存储 | SQLite | 零依赖，结构化 |
| 交互 | CLI 优先 | 专注核心逻辑 |

## 系统架构

```
┌─────────────────────────────────────────────────┐
│                   main.py (CLI 入口)              │
│         接收用户输入，显示结果，管理 session 切换       │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│                agent.py (Agent Loop)              │
│  接收输入 → 构建 context → 调 LLM → 解析响应 →      │
│  判断是工具调用还是最终答案 → 循环或返回               │
└──────┬──────────────┬──────────────┬────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐
│  llm.py  │  │  context.py  │  │   tools/     │
│ 调用DeepSeek│  │ 管理对话历史  │  │ 工具注册+执行 │
│ API 并解析 │  │ 过长时压缩   │  │              │
└──────────┘  └──────────────┘  └──────┬───────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
             ┌──────────┐      ┌──────────┐      ┌──────────┐
             │calculator│      │  search  │      │   todo   │
             │  计算器   │      │ 搜索(mock)│      │ 待办+天气 │
             └──────────┘      └──────────┘      └──────────┘

┌─────────────────────────────────────────────────┐
│              session.py (Session 管理)            │
│      SQLite 存储，支持创建/读取/更新/列表/删除       │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              models.py (数据模型)                  │
│     Pydantic 模型：Message, ToolCall, Session     │
└─────────────────────────────────────────────────┘
```

## 模块设计

### 1. main.py - CLI 入口

**职责：** 用户交互循环，session 管理命令

**功能：**
- 启动时显示欢迎信息和可用命令
- 支持命令：`/new` 新建 session，`/list` 列出 session，`/switch <id>` 切换 session，`/history` 查看历史，`/quit` 退出
- 默认自动创建新 session
- 调用 agent.py 处理用户输入
- 显示 Agent 响应和耗时

### 2. agent.py - Agent Loop 核心

**职责：** 协调 LLM、工具、Context 的核心循环

**流程：**
```
用户输入
    │
    ▼
加载 session history
    │
    ▼
构建 messages（system prompt + history + 新消息）
    │
    ▼
调用 LLM API
    │
    ▼
解析响应
    │
    ├─ 有 tool_call → 执行工具 → 结果追加到 messages → 回到"调用 LLM"
    │
    └─ 无 tool_call → 返回最终答案
    │
    ▼
检查轮次限制（防止无限循环）
    │
    ├─ 超限 → 强制返回，告知用户
    │
    └─ 未超限 → 继续循环
```

**接口：**
```python
def run_agent(user_input: str, session_id: str) -> AgentResult:
    """
    运行 Agent Loop
    
    Args:
        user_input: 用户输入
        session_id: session ID
    
    Returns:
        AgentResult: 包含最终回复、token 使用量、耗时
    """
```

### 3. llm.py - LLM API 封装

**职责：** 封装 DeepSeek API 调用，解析响应

**功能：**
- 调用 DeepSeek Chat Completions API
- 支持 function calling（tools 参数）
- 解析响应：区分纯文本回复和工具调用
- 重试机制（超时、限流）
- 记录 token 使用量

**接口：**
```python
def call_llm(messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
    """
    调用 LLM API
    
    Args:
        messages: 消息列表
        tools: 工具 schema 列表（可选）
    
    Returns:
        LLMResponse: 包含文本回复或工具调用
    """
```

### 4. context.py - Context 管理

**职责：** 构建发送给 LLM 的消息列表，轮次限制，过长压缩

**策略：**
```
发送给 LLM 的 messages 构成：

[System Prompt]                    ← 固定，每轮都带
    │
[压缩的早期摘要]                   ← 如果历史过长，早期内容压缩成摘要
    │
[最近 N 轮对话]                    ← 滑动窗口，默认 N=20
    │
[当前用户输入]                     ← 本次用户输入
```

**压缩策略（基础版）：**
- 当历史超过 `MAX_TURNS`（如 20 轮）时，取最早的一半对话
- 调用 LLM 生成摘要："请用 3-5 句话总结以下对话的要点"
- 用摘要替换原始对话，节省 token

**接口：**
```python
def build_messages(session_history: list[Message], user_input: str) -> list[dict]:
    """
    构建发送给 LLM 的消息列表
    
    Args:
        session_history: session 历史消息
        user_input: 当前用户输入
    
    Returns:
        构建好的 messages 列表
    """

def compress_history(messages: list[dict], max_turns: int = 20) -> list[dict]:
    """
    压缩过长的历史消息
    
    Args:
        messages: 原始消息列表
        max_turns: 最大轮次
    
    Returns:
        压缩后的消息列表
    """
```

### 5. session.py - Session 管理

**职责：** SQLite 存储，支持 CRUD 操作

**数据库 Schema：**
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**接口：**
```python
def create_session(title: str = None) -> str:
    """创建新 session，返回 session ID"""

def get_session(session_id: str) -> list[Message]:
    """获取 session 历史消息"""

def add_message(session_id: str, role: str, content: str, 
                tool_call_id: str = None, tool_name: str = None):
    """向 session 添加消息"""

def list_sessions() -> list[Session]:
    """列出所有 session"""

def delete_session(session_id: str):
    """删除 session"""
```

### 6. tools/ - 工具系统

#### tools/registry.py - 工具注册表

**职责：** 管理工具注册，生成 OpenAI function calling 格式

**机制：**
```python
# 装饰器注册
@register_tool(
    name="calculator",
    description="执行数学计算",
    parameters={...}
)
def calculator(expression: str) -> str:
    ...

# 自动生成 tools 列表
def get_tools_schema() -> list[dict]:
    """返回 OpenAI function calling 格式的 tools 列表"""

def execute_tool(tool_name: str, arguments: dict) -> str:
    """执行指定工具，返回结果"""
```

#### tools/calculator.py - 计算器

```python
@register_tool(
    name="calculator",
    description="执行数学计算，支持加减乘除、幂运算等",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，如 '2 + 3 * 4'"
            }
        },
        "required": ["expression"]
    }
)
def calculator(expression: str) -> str:
    """安全执行数学表达式"""
```

#### tools/search.py - 搜索（Mock）

```python
@register_tool(
    name="search",
    description="搜索网络信息（当前为 mock 实现）",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["query"]
    }
)
def search(query: str) -> str:
    """返回 mock 搜索结果"""
```

#### tools/todo.py - 待办 + 天气

```python
@register_tool(
    name="todo",
    description="管理待办事项",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete"],
                "description": "操作类型"
            },
            "content": {
                "type": "string",
                "description": "待办内容（add 时必填）"
            },
            "todo_id": {
                "type": "integer",
                "description": "待办 ID（complete 时必填）"
            }
        },
        "required": ["action"]
    }
)
def todo(action: str, content: str = None, todo_id: int = None) -> str:
    """管理待办事项"""

@register_tool(
    name="get_weather",
    description="查询天气（mock 实现）",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称"
            }
        },
        "required": ["city"]
    }
)
def get_weather(city: str) -> str:
    """返回 mock 天气信息"""
```

### 7. models.py - 数据模型

```python
from pydantic import BaseModel
from datetime import datetime

class Message(BaseModel):
    id: int | None = None
    session_id: str
    role: str  # 'user' | 'assistant' | 'system' | 'tool'
    content: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: datetime | None = None

class Session(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict

class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    usage: dict | None = None

class AgentResult(BaseModel):
    reply: str
    tokens_used: int
    duration: float
    turns: int
```

### 8. config.py - 配置管理

```python
import os
from dataclasses import dataclass

@dataclass
class Config:
    # LLM 配置
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    
    # Agent 配置
    max_turns: int = 10          # 单次对话最大工具调用轮次
    max_context_turns: int = 20  # context 保留的最大轮次
    max_retries: int = 2         # LLM 调用重试次数
    
    # Session 配置
    db_path: str = "agent.db"
    
    # System Prompt
    system_prompt: str = """你是一个有用的 AI 助手。你可以使用工具来帮助用户完成任务。
当需要使用工具时，请调用相应的函数。
当不需要使用工具时，直接回复用户。"""
```

## 异常处理

| 场景 | 处理方式 |
|------|---------|
| LLM API 超时 | 重试 2 次，仍失败则告知用户 |
| LLM API 限流 | 指数退避重试 |
| 工具执行异常 | 捕获异常，返回错误信息给 LLM |
| LLM 返回格式错误 | 解析失败时重试一次 |
| Session 不存在 | 自动创建新 session |
| SQLite 写入失败 | 日志记录，降级到内存模式 |

## 日志追踪

```
[2026-06-24 22:50:01] [session:abc123] [turn:1] 用户输入: 今天北京天气怎么样？
[2026-06-24 22:50:02] [session:abc123] [turn:1] LLM 请求: model=deepseek-chat, tokens=150
[2026-06-24 22:50:03] [session:abc123] [turn:1] LLM 响应: tool_call → get_weather(city="北京")
[2026-06-24 22:50:03] [session:abc123] [turn:1] 工具执行: get_weather → "晴，25°C"
[2026-06-24 22:50:04] [session:abc123] [turn:1] LLM 请求: model=deepseek-chat, tokens=200
[2026-06-24 22:50:05] [session:abc123] [turn:1] LLM 响应: 最终答案
[2026-06-24 22:50:05] [session:abc123] [turn:1] 完成 (耗时 4.2s, tokens=350)
```

## 测试用例

| 测试类别 | 测试点 |
|---------|--------|
| Agent Loop | 纯对话（不调工具）直接返回答案 |
| Agent Loop | 调用单个工具后返回答案 |
| Agent Loop | 多轮工具调用链（先查天气，再记待办） |
| Agent Loop | 轮次限制触发时强制返回 |
| 工具注册 | 注册新工具后 schema 正确 |
| 工具执行 | calculator 正确计算 |
| 工具执行 | search 返回 mock 结果 |
| 工具执行 | todo 创建/查询待办 |
| 工具执行 | 工具异常被正确捕获 |
| Session | 创建新 session |
| Session | 读取已有 session 历史 |
| Session | 两个 session 互不影响 |
| Context | 超过轮次限制时压缩生效 |
| Context | 压缩后仍能回答早期问题 |
| LLM 解析 | 解析纯文本响应 |
| LLM 解析 | 解析工具调用响应 |
| LLM 解析 | 处理格式错误的响应 |
| 集成测试 | 完整的多轮对话流程 |

## 文件结构

```
minimal-agent-runtime/
├── main.py              # CLI 入口
├── agent.py             # Agent Loop 核心
├── llm.py               # DeepSeek API 调用
├── context.py           # Context 管理 + 压缩
├── session.py           # Session CRUD (SQLite)
├── models.py            # Pydantic 数据模型
├── config.py            # 配置管理
├── tools/
│   ├── __init__.py
│   ├── registry.py      # 工具注册机制
│   ├── calculator.py    # 计算器
│   ├── search.py        # 搜索 (mock)
│   └── todo.py          # 待办 + 天气
├── tests/
│   ├── __init__.py
│   ├── test_agent.py    # Agent Loop 测试
│   ├── test_tools.py    # 工具测试
│   ├── test_session.py  # Session 测试
│   └── test_context.py  # Context 测试
├── logs/                # 日志目录
├── README.md            # 项目说明
├── requirements.txt     # 依赖
└── .env.example         # 环境变量示例
```

## 依赖

```
openai>=1.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
pytest>=7.0.0
```

## 开放问题

这个 Agent 离可用 Agent 还差哪些模块：

1. **进阶 Context 管理**：向量数据库召回、长期记忆、相关性排序
2. **Reminder/定时任务**：Agent 主动提醒用户
3. **更快的响应速度**：流式输出、并行工具调用
4. **状态机**：复杂任务的状态管理（优缺点探讨）
5. **多模态支持**：图片、文件处理
6. **权限控制**：工具调用的权限管理
7. **可观测性**：更完善的 tracing 和监控

# Minimal Agent Runtime

从零实现的最小可用 Agent Runtime。不依赖 LangGraph、OpenHands 等框架，核心 Agent Loop、工具注册、Session 管理、Context 管理全部自行实现。

基于 DeepSeek API（OpenAI 兼容），支持 function calling，LLM 自主决策工具调用。

## Features

- **Agent Loop** — 接收输入 → 调 LLM → 判断是否调工具 → 执行 → 循环或返回
- **工具注册** — 装饰器 `@register_tool` 注册，自动生成 OpenAI function calling schema
- **内置工具** — 计算器（AST 安全求值）、搜索（mock）、待办管理（SQLite 持久化）、天气查询（mock）
- **Session 隔离** — SQLite 存储，多 session 互不影响，随时切换
- **Context 管理** — 滑动窗口 + LLM 摘要压缩，防止 token 超限
- **异常处理** — LLM 调用重试、工具异常捕获、轮次限制
- **执行日志** — 全链路 trace，记录每轮 LLM 调用、工具执行、token 用量

---

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

**CLI 模式：**

```bash
python main.py
```

**Web 模式：**

```bash
python web.py
# 浏览器打开 http://localhost:8000
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `/new` | 新建 session |
| `/list` | 列出所有 session |
| `/switch <id>` | 切换到指定 session |
| `/history` | 查看当前 session 历史 |
| `/delete <id>` | 删除 session |
| `/quit` | 退出程序 |

---

## 系统设计

### 整体架构

```
┌─────────────┐     ┌─────────────┐
│  CLI 入口    │     │  Web 入口    │
│  main.py    │     │  web.py     │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └───────┬───────────┘
               ▼
       ┌──────────────┐
       │   agent.py   │   Agent Loop 核心
       │  run_agent() │
       └──┬────┬───┬──┘
          │    │   │
          ▼    │   ▼
   ┌────────┐  │  ┌────────────┐
   │ llm.py │  │  │ context.py │
   │ DeepSeek│  │  │ 消息构建    │
   │ API    │  │  │ 压缩管理    │
   └────────┘  │  └─────┬──────┘
               ▼        │
        ┌───────────┐   │
        │ session.py│◄──┘
        │ SQLite    │
        └─────┬─────┘
              │
              ▼
     ┌─────────────────┐
     │ tools/registry.py│  工具注册表
     ├─────────────────┤
     │ calculator.py   │  数学计算
     │ search.py       │  搜索 (mock)
     │ todo.py         │  待办管理
     └─────────────────┘
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `agent.py` | Agent Loop：接收输入 → 调 LLM → 解析响应 → 执行工具 → 循环或返回 |
| `llm.py` | 封装 DeepSeek API，支持 function calling，指数退避重试 |
| `context.py` | 构建发送给 LLM 的 messages，滑动窗口截断 + LLM 摘要压缩 |
| `session.py` | SQLite 持久化 session 和 messages，支持 CRUD |
| `tools/registry.py` | 工具注册机制，装饰器模式，自动生成 OpenAI schema |
| `config.py` | 全局配置，从环境变量读取 |

### Agent Loop 流程

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

每次循环检查轮次限制（默认 10 轮），超过则强制返回。

---

## Memory 召回时机与放置方式

### 召回时机

**每次用户发送消息时触发召回**，具体流程：

1. 用户发送消息
2. 从 SQLite 加载该 session 的**全部历史消息**
3. 如果历史超过滑动窗口（默认 40 条），对早期消息调用 LLM 生成摘要
4. 构建最终 messages 发送给 LLM

### 放置方式（Context 结构）

发送给 LLM 的 messages 结构如下：

```
┌─────────────────────────────────────────┐
│ [0] system                              │  ← 固定 System Prompt（定义 Agent 角色）
├─────────────────────────────────────────┤
│ [1] system (可选)                       │  ← 压缩摘要（仅当历史过长时出现）
│     "以下是之前对话的摘要：\n..."        │
├─────────────────────────────────────────┤
│ [2] user     "在吗？"                   │  ← 滑动窗口内的历史消息
│ [3] assistant "在的！"                   │     最近 N 轮（默认 20 轮 = 40 条）
│ [4] user     "帮我查天气"               │
│ [5] assistant {tool_calls: [...]}       │     包含 assistant 的 tool_calls 还原
│ [6] tool     {天气结果}                  │     包含 tool 执行结果
│ [7] assistant "北京今天晴..."            │
├─────────────────────────────────────────┤
│ [8] user     "帮我记到待办"              │  ← 当前用户输入（始终在最后）
└─────────────────────────────────────────┘
```

### 压缩策略

| 策略 | 触发条件 | 做法 |
|------|---------|------|
| 滑动窗口 | 历史 > 40 条 | 保留最近 40 条，丢弃更早的 |
| LLM 摘要 | 滑动窗口触发时 | 对被截断的早期消息调用 LLM 生成摘要，以 system 消息插入 |
| 降级策略 | 摘要生成失败 | 截取前 6 条消息的片段作为摘要 |

### 为什么这样设计

- **system prompt 在最前面**：LLM 对开头的指令权重最高
- **摘要用 system role**：区分"背景信息"和"实际对话"
- **当前输入在最后**：LLM 对最近的输入关注度最高（recency bias）
- **tool_calls 还原**：确保 API 格式正确，避免 400 错误

---

## 工具系统

### 注册机制

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

### 内置工具

| 工具 | 功能 | 数据源 |
|------|------|--------|
| `calculator` | 数学表达式求值（AST 安全） | 真实计算 |
| `search` | 搜索网络信息 | mock（预设数据） |
| `todo` | 待办事项管理（增/列/完成） | SQLite 持久化，按 session 隔离 |
| `get_weather` | 查询城市天气 | mock（预设数据） |

### 工具上下文注入

工具函数可接收 `session_id` 等上下文参数，用于数据隔离：

```python
# agent.py 调用时传入上下文
registry.execute(tc.name, tc.arguments, context={"session_id": session_id})

# todo.py 接收 session_id 实现按 session 隔离
def todo(action: str, ..., session_id: str = "default") -> str:
    # 只操作该 session 的待办
```

---

## Session 管理

### 数据存储

所有数据存储在 `agent.db`（SQLite），通过 `session_id` 隔离：

```
agent.db
├── sessions 表：会话列表（id, title, created_at, updated_at）
├── messages 表：所有消息（session_id, role, content, tool_call_id）
└── todos 表：待办事项（session_id, content, done）
```

### 隔离验证

```
窗口 1 (session-A)：               窗口 2 (session-B)：
  "帮我查天气"                       "帮我写周报"
  → 添加待办 #1: 查天气              → 添加待办 #2: 写周报
  /list → 只看到 #1                  /list → 只看到 #2
```

---

## Testing

不需要 API Key 的测试（工具、Session、Context）：

```bash
pytest tests/test_tools.py tests/test_session.py tests/test_context.py -v
```

全部测试（需要 `DEEPSEEK_API_KEY` 环境变量）：

```bash
pytest tests/ -v
```

| Module | Tests | Coverage |
|--------|-------|----------|
| Tools | 18 | 注册、计算器、搜索、待办、天气 |
| Session | 8 | CRUD、隔离、消息操作 |
| Context | 6 | 构建、压缩、滑动窗口 |
| Agent | 7 | 对话、工具调用、多轮链、session 连续性、轮次限制、session 隔离 |

---

## Project Structure

```
minimal-agent-runtime/
├── main.py              # CLI 入口，交互循环
├── web.py               # FastAPI Web 后端 + 前端页面
├── agent.py             # Agent Loop 核心逻辑
├── llm.py               # DeepSeek API 封装 + 重试
├── context.py           # 消息构建 + 滑动窗口压缩
├── session.py           # SQLite Session CRUD
├── models.py            # Pydantic 数据模型
├── config.py            # 全局配置
├── index.html           # Web 前端页面
├── tools/
│   ├── registry.py      # 工具注册表 + 装饰器
│   ├── calculator.py    # 计算器（AST 安全求值）
│   ├── search.py        # 搜索（mock）
│   └── todo.py          # 待办管理（SQLite 持久化）+ 天气（mock）
├── tests/
│   ├── test_agent.py    # Agent Loop 集成测试
│   ├── test_tools.py    # 工具单元测试
│   ├── test_session.py  # Session 测试
│   └── test_context.py  # Context 测试
├── docs/
│   └── AI_PROMPT.md     # AI Prompt 与问题解决记录
└── logs/                # 运行日志
```

---

## 开放问题：离可用 Agent 还差哪些模块

### 一、核心能力缺口

| 模块 | 当前状态 | 生产需要 | 优先级 |
|------|---------|---------|--------|
| **流式输出** | 无 | SSE/WebSocket 逐 token 输出，用户不用等完整回复 | 🔴 高 |
| **并行工具调用** | 串行执行 | 多工具同时执行，减少等待时间 | 🔴 高 |
| **向量记忆/RAG** | 仅滑动窗口 | 长期记忆 + 语义召回，跨 session 记住用户偏好 | 🔴 高 |
| **工具执行超时** | 无 | 防止工具 hang 住整个 loop | 🟡 中 |
| **认证鉴权** | 无 | 多用户隔离，API Key 管理 | 🟡 中 |
| **并发安全** | 无锁 | 多请求同时操作同一 session 的竞态问题 | 🟡 中 |

### 二、进阶 Context 管理

**当前方案**：滑动窗口 + LLM 摘要（system role 插入）

**可优化方向**：
- **分层记忆**：短期（当前对话）+ 中期（本次 session 摘要）+ 长期（向量数据库）
- **重要信息提取**：用户名字、偏好、关键结论单独存储，每次必带
- **tool 结果压缩**：长结果（如搜索返回）截取关键段落，不全量塞入 context
- **多条 system 消息合并**：避免 OpenAI API 对多条 system 消息的处理差异

### 三、Reminder 机制

**需要新增的能力**：
- 定时调度器（cron / APScheduler）
- 用户说"提醒我明天开会" → 解析时间 → 写入调度队列
- 到时间触发 → 推送通知（WebSocket / 消息队列）
- 当前架构完全没有异步触发能力，需要新增事件循环层

### 四、更快的响应速度

| 优化点 | 当前 | 优化后 |
|--------|------|--------|
| 输出方式 | 等完整回复再返回 | 流式逐 token 输出 |
| 工具执行 | 串行 | 并行（asyncio.gather） |
| LLM 调用 | 每次全量 prompt | prompt cache（DeepSeek 支持） |
| 工具结果 | 每次重新计算 | 缓存（如天气 5 分钟内复用） |

### 五、状态机的优缺点

**优点**：
- 状态转换明确（plan → act → observe → reflect），可测试、可恢复
- 每个状态有明确的输入输出，便于 debug
- 支持复杂任务的分支和回退

**缺点**：
- 简单场景过度设计（用户问"1+1"也要走 plan → act 流程）
- 状态爆炸：任务复杂时状态数指数增长
- 灵活性差：LLM 擅长自由推理，状态机限制了它的能力

**建议**：简单 Agent 用纯 loop（当前方案），复杂 Agent（如 Devin）用状态机 + LLM 混合决策。

---

## Logging

运行日志自动保存到 `logs/web.log`，记录每轮的 LLM 调用、工具执行和 token 用量：

```
[2026-06-24 22:50:01] INFO [session:abc123] [turn:1] 调用 LLM
[2026-06-24 22:50:02] INFO [session:abc123] [turn:1] 执行工具: get_weather({"city": "北京"})
[2026-06-24 22:50:02] INFO [session:abc123] [turn:1] 工具结果: {"city": "北京", ...}
[2026-06-24 22:50:03] INFO [session:abc123] 完成 (耗时 2.1s, tokens=350, turns=2)
```

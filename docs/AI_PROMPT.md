# AI Prompt 与问题解决记录

## 1. AI 使用范围

本项目允许使用 AI 工具辅助开发。核心 Agent Runtime 未使用 LangGraph、OpenHands、OpenClaw 等框架。

**AI 辅助的部分：**
- 代码骨架生成（模块拆分、函数签名、数据模型）
- 测试用例生成
- Bug 排查与修复方案
- README 草稿整理

**我负责的部分：**
- 模块拆分的最终决策（哪些合在一起、哪些拆开）
- 技术方案选型（SQLite vs 文件、滑动窗口 vs 向量召回）
- Bug 的根因判断（不是直接丢报错给 AI，而是先定位到序列化层）
- 测试用例的覆盖范围定义
- 代码整合与调试

---

## 2. 项目结构设计

### Prompt

```
我要从零实现一个最小 Agent Runtime，不依赖现有 Agent 框架。
请先 brainstorming 探索模块拆分方案，要求：
1. 核心 Agent Loop 独立于入口（CLI/Web）
2. 工具注册机制支持动态扩展，新增工具不改主流程
3. Session 数据持久化，支持多窗口独立
4. Context 管理有滑动窗口和基础压缩

输出：模块职责表 + 依赖关系图 + 每个模块的核心接口定义
```

### AI 建议

AI 提出了两种方案：

**方案 A — 扁平结构：**
```
agent.py, llm.py, context.py, session.py, tools/registry.py
```

**方案 B — 包结构：**
```
agent/core.py, agent/llm.py, agent/context.py, tools/base.py
```

### 我的决策

选择方案 A（扁平结构）。原因：
- 项目规模小（6 个核心文件），包结构增加 import 复杂度但收益不大
- 入口文件（main.py / web.py）直接 import agent.py，路径清晰
- 面试场景下，扁平结构更容易让面试官快速理解

工具系统选择了方案 A 的 `tools/` 子目录，因为工具会持续增加，独立目录便于管理。

### 相关文件

- `agent.py` — Agent Loop 核心
- `tools/registry.py` — 工具注册表

---

## 3. 工具注册机制

### Prompt

```
设计工具注册机制，要求：
1. 每个工具有 name、description、parameters（JSON Schema）
2. 新增工具只需写函数 + 加装饰器，不改 agent.py
3. 自动生成 OpenAI function calling 格式的 tools schema

请对比装饰器注册 vs 配置文件注册 vs 类继承三种方案的 trade-off。
然后用 TDD 方式：先写测试定义注册、schema 生成、执行三个接口的预期行为，再实现。
```

### AI 建议

AI 推荐装饰器方案：
```python
@register_tool(name="calculator", description="...", parameters={...})
def calculator(expression: str) -> str:
    ...
```

理由：Python 生态惯例（Flask 的 `@app.route`、pytest 的 `@pytest.fixture`），代码和元数据在一起，不易遗漏。

### 我的决策

采用装饰器方案。补充了一个设计决策：`registry.execute()` 接收 `context` 参数，允许注入 `session_id` 等运行时上下文。这样工具函数可以按 session 隔离数据，而不需要在注册时硬编码 session 逻辑。

```python
# agent.py 调用时注入上下文
registry.execute(tc.name, tc.arguments, context={"session_id": session_id})

# 工具函数通过 **kwargs 接收
def todo(action: str, session_id: str = "default", **kwargs) -> str:
    ...
```

### 相关文件

- `tools/registry.py` — 注册表 + execute 方法
- `tools/calculator.py` — 示例工具

---

## 4. Tool Calls 序列化问题

### 问题

Agent 执行工具调用后，第二次请求报 400 错误：
```
Messages with role 'tool' must be a response to a preceding message with 'tool_calls'
```

### 我的排查思路

1. 先看数据库消息格式 → assistant 消息是纯文本，没有 tool_calls 字段
2. 追溯保存逻辑 → `agent.py` 把 tool_calls 序列化到 content JSON 中
3. 追溯加载逻辑 → `context.py` 的 `_format_history` 只读 content 字符串，没解析 JSON
4. 定位根因 → 序列化和反序列化不对称

### Prompt

```
OpenAI API 要求 tool 消息必须紧跟带 tool_calls 的 assistant 消息。
我的 Agent 在持久化时把 tool_calls 序列化到了 assistant 消息的 content JSON 中，
但加载历史时没有还原 tool_calls 字段，导致 tool 消息变成"孤立"的。

请分析：
1. 这个问题的根本原因是什么？
2. 如何在 _format_history 中正确还原 tool_calls？
3. 如果 assistant 消息同时触发多个 tool_calls（如一次添加 3 条待办），
   如何确保所有 tool 消息都被正确关联？
```

### AI 建议

AI 给出了完整的 `_format_history` 重写方案，包括：
- 解析 assistant content 中的 JSON
- 用后续 tool 消息的 tool_call_id 匹配
- 处理多工具调用时跳过已消费的索引

### 我的决策

采纳核心逻辑，但修改了两点：
1. 优先使用 JSON 中保存的 tool_call id（因为 `agent.py` 保存时已经存了），其次才用 tool 消息的 id
2. 对孤立的 tool 消息（前面没有 assistant tool_calls）选择跳过而不是报错，提高健壮性

### 相关文件

- `context.py` — `_format_history` 函数
- `agent.py` — tool_calls 序列化到 content

---

## 5. Session 隔离与 Todo 持久化

### 问题

待办工具的 `_todos` 是全局内存列表，所有 session 共享。窗口 1 添加的待办，窗口 2 也能看到。

### 我的排查思路

1. 看 `tools/todo.py` → `_todos: list[dict]` 是模块级全局变量
2. 看 `registry.execute()` → 没有传入 session 上下文
3. 判断：需要两层修改 — 工具层按 session 隔离 + 注册表层支持上下文注入

### Prompt

```
工具的数据隔离有几种方案：
1. 工具内部维护 dict[session_id, data]（内存）
2. 工具直接读写 SQLite，按 session_id 过滤
3. 每个 session 独立的工具实例

请对比三种方案的 trade-off，并考虑：数据持久化、进程重启恢复、实现复杂度。
```

### AI 建议

AI 推荐方案 2（SQLite），理由：已有 session.py 的 SQLite 基础设施，复用连接；数据持久化；按 session_id 过滤是 SQL 的基本操作。

### 我的决策

采用方案 2。实现上：
- Todo 表加 `session_id` 字段，所有查询带 `WHERE session_id = ?`
- `registry.execute()` 加 `context` 参数，agent.py 传入 session_id
- 工具函数通过 `**kwargs` 接收上下文，不破坏原有签名

同时把天气工具从 `todo.py` 拆到独立的 `weather.py`，因为一个文件塞两个不相关的工具违反单一职责。

### 相关文件

- `tools/todo.py` — SQLite 持久化 + session 隔离
- `tools/weather.py` — 从 todo.py 拆出
- `tools/registry.py` — execute 方法加 context 参数
- `agent.py` — 调用时传入 session_id

---

## 6. Context 管理设计

### Prompt

```
Context 管理需要解决：
1. 发送给 LLM 的 messages 结构是什么？
2. 历史过长时如何压缩？
3. 工具调用的中间结果放在 context 的什么位置？

请设计 build_messages 函数的输出格式，并说明每部分的设计理由。
```

### AI 建议

AI 给出了分层结构：
```
[system prompt] → 固定，定义 Agent 角色
[压缩摘要]      → 可选，早期对话的 LLM 摘要
[滑动窗口历史]  → 最近 N 轮对话原文
[当前用户输入]  → 始终在最后
```

压缩策略：超过 `max_context_turns * 2` 条时，对早期消息调用 LLM 生成摘要，失败时降级为截取前几条消息片段。

### 我的决策

采纳分层结构。补充了一个设计决策：摘要以 `system` role 插入，而不是 `user`/`assistant`。原因：
- system 消息在 OpenAI API 中权重最高，LLM 更可能参考
- 语义上区分"背景信息"和"实际对话"
- 但需要注意 OpenAI 对多条 system 消息的处理可能因模型而异

### 相关文件

- `context.py` — `build_messages`、`compress_history`、`_generate_summary`

---

## 7. 测试设计

### Prompt

```
为 Agent Runtime 设计测试用例，要求：
1. 工具层和 Session 层的测试不需要真实 API Key
2. Agent Loop 集成测试需要 API Key，无 Key 时自动跳过
3. 覆盖场景：纯对话、单工具调用、多工具链、session 连续性、session 隔离、轮次限制
4. Context 压缩测试用 mock LLM，避免真实 API 依赖

请先列出测试矩阵，再逐个实现。
```

### 我的决策

测试分三层：
- **单元测试**（test_tools.py, test_session.py）：不依赖 API，测试工具注册、CRUD、隔离
- **Context 测试**（test_context.py）：用 `unittest.mock.patch` mock LLM 调用，测试消息构建和压缩逻辑
- **集成测试**（test_agent.py）：需要真实 API Key，`pytest.mark.skipif` 控制

工具测试中，Todo 测试使用独立的 `session_id`（如 `"test-tools-todo"`），避免测试间数据污染。

### 相关文件

- `tests/test_tools.py` — 工具单元测试
- `tests/test_session.py` — Session 测试
- `tests/test_context.py` — Context 测试（mock LLM）
- `tests/test_agent.py` — Agent 集成测试（需 API Key）

---

## 8. 总结

AI 工具帮助我快速搭建了项目骨架和处理了繁琐的细节（如 OpenAI API 格式要求、SQLite 操作），但本项目的核心目标是理解并实现 Agent Runtime 的关键机制：

- **LLM 决策**：通过 function calling schema 让 LLM 自主选择工具
- **工具调用**：装饰器注册 + 上下文注入 + 按 session 隔离
- **循环控制**：while loop + 轮次限制 + tool_calls 判断
- **Session 隔离**：SQLite 按 session_id 分离，多窗口互不影响
- **Context 管理**：滑动窗口 + LLM 摘要压缩 + 降级策略
- **异常处理**：LLM 重试、工具异常捕获、API 格式校验

其中最让我加深理解的是 **tool_calls 的序列化/反序列化对称性问题** — 看似简单的"存进去再读出来"，在 API 格式约束下变成了需要仔细设计的状态机。

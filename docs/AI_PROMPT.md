# AI Prompt 与问题解决记录

记录开发过程中使用 AI 辅助的关键 prompt、遇到的问题和解决方案。

---

## 问题 1：Conda 编码错误

### 现象

```
UnicodeEncodeError: 'gbk' codec can't encode character '�' in position 861
```

Windows 中文系统下，conda 激活时 GBK 编码无法输出 Unicode 字符。

### Prompt

```
conda 报错 UnicodeEncodeError: 'gbk' codec can't encode character '�'
```

### 解决方案

1. 设置 `PYTHONUTF8=1` 环境变量（永久）
2. 设置 `CONDA_UTF8=1` 环境变量（永久）
3. 清理 PATH 中损坏的 Unicode 条目（`C:\Users\????\...`）
4. 在 PowerShell profile 中预设 `PYTHONUTF8=1`，确保 conda 执行前生效

### 根因

Windows PATH 环境变量中存在损坏的 Unicode 条目（`�ƺ��`），conda 输出时遇到无法编码的字符。

---

## 问题 2：Tool Calls 400 错误

### 现象

```
Error code: 400 - Messages with role 'tool' must be a response to a preceding message with 'tool_calls'
```

Agent 执行第二个工具调用时，DeepSeek API 返回 400 错误。

### Prompt

```
LLM 调用失败: Messages with role 'tool' must be a response to a preceding message with 'tool_calls'
```

### 排查过程

1. 检查数据库中的消息格式
2. 发现 assistant 消息的 content 是纯文本，不是 JSON 格式
3. 追溯代码：`agent.py` 保存时把 tool_calls 序列化到 content JSON 中
4. 但 `_format_history` 加载时没有还原 tool_calls 字段

### 根因

**保存时**：assistant 消息的 tool_calls 被序列化为 JSON 存入 content
```python
# agent.py
assistant_content = json.dumps({
    "text": response.content,
    "tool_calls": [{"name": tc.name, "arguments": tc.arguments}]
})
```

**加载时**：`_format_history` 只读 content 字符串，没有解析 JSON 中的 tool_calls
```python
# context.py - 旧代码
elif msg.role == "assistant":
    entry = {"role": "assistant", "content": msg.content}  # 缺少 tool_calls
```

导致 tool 消息变成"孤立"的（前面没有带 tool_calls 的 assistant 消息），API 拒绝。

### 解决方案

修改 `context.py` 的 `_format_history`：

1. 解析 assistant 消息 content 中的 JSON，还原 tool_calls
2. 用后续 tool 消息的 tool_call_id 匹配
3. 跳过孤立的 tool 消息（前面没有 assistant tool_calls 的）

```python
# 还原 tool_calls
data = json.loads(content)
if "tool_calls" in data:
    content = data.get("text", "")
    parsed_tool_calls = data["tool_calls"]

# 检查后续消息是否有 tool 消息
if parsed_tool_calls and history[i + 1].role == "tool":
    # 用 tool 消息的 tool_call_id 构建完整的 tool_calls
    tool_calls = [...]
    entry = {"role": "assistant", "content": content, "tool_calls": tool_calls}
```

同时修改 `agent.py`，保存时包含 tool_call 的 id：
```python
tool_calls_info = [
    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
    for tc in response.tool_calls
]
```

---

## 问题 3：Todo 跨 Session 共享

### 现象

窗口 1 添加的待办，在窗口 2 也能看到。

### Prompt

```
代办是啥？也是工具吗？能真实执行吗？现在每一个session要存吗？
```

### 根因

`_todos` 是全局内存列表，所有 session 共享同一份数据。

### 解决方案

1. **按 session 隔离**：`_todos` 从 `list` 改为 `dict[session_id, list]`
2. **工具上下文注入**：`registry.execute()` 新增 `context` 参数，透传 `session_id`
3. **SQLite 持久化**：从内存改为 SQLite `todos` 表，重启不丢

```python
# tools/registry.py
def execute(self, tool_name, arguments, context=None):
    kwargs = {**arguments}
    if context:
        kwargs.update(context)
    result = info.func(**kwargs)

# agent.py
registry.execute(tc.name, tc.arguments, context={"session_id": session_id})

# tools/todo.py - SQLite 存储
def todo(action, ..., session_id="default"):
    # 按 session_id 查询/插入
```

---

## 问题 4：Session 消息格式不一致

### 现象

旧数据中 assistant 消息是纯文本，新数据是 JSON 格式。加载历史时格式不统一。

### 解决方案

`_format_history` 兼容两种格式：
- 尝试 `json.loads(content)` 解析
- 如果是 JSON 且包含 `tool_calls` → 还原 tool_calls 字段
- 如果解析失败 → 当作纯文本处理

---

## 开发中使用的 AI 辅助

| 场景 | 使用方式 |
|------|---------|
| 问题排查 | 描述错误现象，让 AI 分析根因 |
| 代码审查 | 让 AI 检查 tool_calls 序列化/反序列化逻辑 |
| 架构讨论 | 讨论 Memory 召回时机、Context 结构设计 |
| 文档生成 | 让 AI 根据代码生成 README、测试用例 |
| Bug 修复 | 描述问题，AI 提供修改方案和代码 |

---

## 关键教训

1. **序列化/反序列化要对称**：保存时用 JSON，加载时一定要解析 JSON，不能当纯文本
2. **API 格式要求严格**：OpenAI 的 tool messages 必须紧跟 assistant tool_calls，不能有孤立的
3. **数据隔离要从设计开始**：工具的 session_id 注入应该在第一天就做，不要事后补
4. **SQLite 比内存可靠**：内存数据进程重启就丢，持久化是基本要求

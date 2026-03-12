# com.celiang.hlsc.service.ai.chatagent

话痨说车对话 Agent

## 消息持久化架构

### 存储层

| 文件 | 用途 | 写入方式 |
|------|------|----------|
| `messages.jsonl` / SQLite | 消息工作集（每次请求加载） | append + compact 时全量覆写 |
| `transcript.jsonl` | 审计日志（仅修复时读取） | append-only，从不删除 |

通过 `MEMORY_SERVICE_TYPE` 环境变量切换实现：
- `fs`（默认）— jsonl 文件持久化（FileMemoryMessageService）
- `sqlite` — SQLite WAL 模式，每用户一个 db（SqliteMemoryMessageService）

### 读写频率

- **读取**：每 session 生命周期内首次请求读一次文件/db，之后命中内存缓存
- **写入**：每次请求结束时 append 一次（transcript + messages 各一次）
- **全量覆写**：仅在 compact 触发时

### 加载时自动修复

从文件/db 加载消息时，检测 tool_call/tool_result 配对问题：
1. 从 transcript.jsonl 查找缺失的 tool_result
2. 找不到则补虚拟 tool_result（`[工具调用已取消，结果不可用]`）
3. 修复后回写存储

### 可观测性

基于 OpenTelemetry 标准，通过 Logfire 采集 traces/logs：
- `LOGFIRE_ENABLED=true` 启用
- `LOGFIRE_ENDPOINT` 配置上报地址

### Interrupt 机制

ask_user 工具通过 Temporal Workflow 实现 interrupt/resume，使用前需配置：
- `TEMPORAL_ENABLED=true`
- `TEMPORAL_HOST=localhost:7233`（Temporal Server 地址）

## SSE 事件协议

### 事件结构

所有事件通过 SSE（Server-Sent Events）推送，格式：

```
event: {type}
data: {json}
```

事件 JSON 结构：

```json
{
  "session_id": "会话 ID",
  "request_id": "请求 ID",
  "type": "事件类型",
  "data": {},
  "timestamp": 1710000000000,
  "finish_reason": null,
  "agent_name": "main",
  "agent_path": "main",
  "parent_tool_call_id": null
}
```

### 事件类型

| type | 说明 | data 字段 |
|------|------|-----------|
| `chat_request_start` | 请求开始 | `task_id` |
| `text` | LLM 文本片段（流式） | `content` |
| `tool_call_start` | 工具调用开始 | `tool_name`, `tool_call_id` |
| `tool_call_args` | 工具参数片段（流式） | `args_chunk` |
| `tool_result` | 工具执行结果 | `tool_name`, `tool_call_id`, `result` |
| `tool_result_detail` | 卡片数据 | `tool_call_id`, `detail_type`, `data` |
| `interrupt` | HITL 中断，等待用户回复 | `question`, `type`, `interrupt_id`, `interrupt_key` |
| `error` | 错误 | `message` |
| `chat_request_end` | 请求结束 | — |

### Subagent 层级机制

当 main agent 的某个 tool 内部调用 subagent 时，subagent 的事件通过两个字段表达层级关系：

- **`agent_path`**：以 `|` 分隔的 agent 层级路径，如 `"main"`, `"main|inquiry"`, `"main|inquiry|compare"`
- **`parent_tool_call_id`**：触发此 subagent 的**直接父 agent** 中的 `tool_call_id`

#### Main Agent 事件示例

```json
{"type": "text",            "agent_path": "main", "parent_tool_call_id": null,
 "data": {"content": "好的，我来帮你询价"}}

{"type": "tool_call_start", "agent_path": "main", "parent_tool_call_id": null,
 "data": {"tool_name": "run_inquiry", "tool_call_id": "call_A"}}

{"type": "tool_result",     "agent_path": "main", "parent_tool_call_id": null,
 "data": {"tool_name": "run_inquiry", "tool_call_id": "call_A", "result": "询价完成"}}
```

Main agent 事件的 `parent_tool_call_id` 始终为 `null`。

#### Subagent 事件示例（在 run_inquiry tool 内部）

```json
{"type": "text",            "agent_path": "main|inquiry", "parent_tool_call_id": "call_A",
 "data": {"content": "正在查询匹配项目..."}}

{"type": "tool_call_start", "agent_path": "main|inquiry", "parent_tool_call_id": "call_A",
 "data": {"tool_name": "search_parts", "tool_call_id": "call_B"}}

{"type": "tool_result",     "agent_path": "main|inquiry", "parent_tool_call_id": "call_A",
 "data": {"tool_name": "search_parts", "tool_call_id": "call_B", "result": "找到3个配件"}}

{"type": "interrupt",       "agent_path": "main|inquiry", "parent_tool_call_id": "call_A",
 "data": {"question": "确认方案A？", "type": "confirm"}}
```

所有 subagent 事件的 `parent_tool_call_id` 指向 main agent 中 `"call_A"` 这个 tool call。

#### Sub-subagent 事件示例（inquiry 的 tool 内部再调 subagent）

```json
{"type": "text",            "agent_path": "main|inquiry|compare", "parent_tool_call_id": "call_B",
 "data": {"content": "比价中..."}}
```

`parent_tool_call_id` 指向 inquiry agent 中的 `"call_B"`，无限嵌套同理。

#### 前端渲染规则

1. `parent_tool_call_id == null` → 顶层渲染
2. `parent_tool_call_id == "call_X"` → 塞到 `call_X` 的 tool 卡片内部渲染
3. 按 `agent_path` 的 `|` 分隔层级，支持无限嵌套

```
消息: "好的，我来帮你询价"               ← agent_path="main"
工具卡片: run_inquiry (call_A)           ← agent_path="main"
  ├── 文本: "正在查询匹配项目..."         ← agent_path="main|inquiry", parent=call_A
  ├── 工具: search_parts (call_B)        ← agent_path="main|inquiry", parent=call_A
  │   └── 结果: "找到3个配件"
  ├── 文本: "找到方案，请确认"
  └── 中断: "确认方案A？"
工具结果: run_inquiry → "询价完成"        ← agent_path="main"
消息: "已为您完成询价"                   ← agent_path="main"
```

## A2A 协议支持

本服务同时暴露 A2A（Agent-to-Agent）协议端点，可作为 subagent 被其他 agent 调用：

- `GET /.well-known/agent.json` — AgentCard 能力发现
- `POST /a2a` — A2A JSON-RPC 端点（message/send、message/stream）

内部事件到 A2A 的映射：

| 内部事件 | A2A 对应 |
|---------|----------|
| `text` | `artifact(TextPart)` |
| `interrupt` | `status: input-required` |
| `tool_result_detail`（卡片） | `artifact(DataPart)` |
| `chat_request_end` | `status: completed` |

### 已知限制

- **Interrupt 依赖 Temporal**：未配置 Temporal 时 ask_user 工具不可用
- **Interrupt 期间重启会丢失当前请求的消息**：持久化发生在请求结束时（agent loop 退出后），如果 ask_user interrupt 等待期间后端重启，本次请求的所有消息（用户输入 + LLM 回复 + 工具调用）不会被写入文件。重启后前端 reply interrupt 会收到 410，用户需重新发送消息。之前的历史消息不受影响。

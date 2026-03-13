# com.celiang.hlsc.service.ai.chatagent

话痨说车对话 Agent

## 快速启动

### 1. 启动后端

每个 Agent 通过各自目录下的 `server.py` 启动，默认加载同目录 `.env.local`：

```bash
# MainAgent（端口 8100）
uv run python src/hlsc/mainagent/server.py

# PriceFinder Subagent（端口 8101）
uv run python src/hlsc/subagents/price_finder/server.py
```

也可指定配置文件或覆盖端口：

```bash
uv run python src/hlsc/mainagent/server.py --env src/hlsc/mainagent/.env.uat
uv run python src/hlsc/mainagent/server.py --port 9000
```

VS Code 用户直接 F5，选择 **MainAgent** 或 **PriceFinder** 配置。

### 2. 启动前端

前端是公用的 React SPA，通过 Vite proxy 连接不同后端：

```bash
cd web

# 连接 MainAgent（默认 proxy → localhost:8100）
npm run dev

# 连接 PriceFinder Subagent
VITE_PROXY_TARGET=http://127.0.0.1:8101 VITE_PORT=3101 npm run dev
```

打开浏览器：
- MainAgent: http://localhost:3100
- PriceFinder: http://localhost:3101

### 3. 前置依赖

- **Temporal Server**（ask_user interrupt 机制依赖）：`TEMPORAL_ENABLED=true`
- **Nacos**（生产配置中心）：本地开发用 `USE_NACOS=FALSE`

## 项目结构

```
src/
├── sdk/                              # 通用框架（可复用）
│   ├── agent.py                      # Agent 纯逻辑层
│   ├── agent_app.py                  # AgentApp 部署容器
│   ├── config.py                     # 配置类
│   ├── prompt_loader.py              # PromptLoader 协议
│   └── _agent/, _server/, ...        # 内部实现
│
├── hlsc/                             # 话痨说车业务
│   ├── mainagent/
│   │   ├── server.py                 # 启动入口
│   │   ├── app.py                    # Agent 工厂
│   │   ├── .env.local                # 本地配置
│   │   ├── prompt_loader.py          # 主 Agent PromptLoader
│   │   ├── hlsc_context.py           # 业务上下文
│   │   └── hlsc_core.py              # 核心模型（CarInfo 等）
│   │
│   └── subagents/
│       └── price_finder/
│           ├── server.py             # 启动入口
│           ├── tools.py              # 比价工具
│           └── .env.local            # 本地配置
│
web/                                  # 公用前端（React + Vite）
```

## 配置说明

每个 Agent 目录下有完整的 `.env.local`，包含所有配置项。生产环境通过 Nacos 下发。

| 配置项 | 说明 | MainAgent 默认 | PriceFinder 默认 |
|--------|------|---------------|-----------------|
| `SERVER_PORT` | 服务端口 | 8100 | 8101 |
| `USER_FS_DIR` | 用户数据目录 | data | src/hlsc/subagents/price_finder/data |
| `MEMORY_SERVICE_TYPE` | 存储实现 | sqlite | fs |
| `TEMPORAL_ENABLED` | Temporal 开关 | true | true |
| `PRICE_FINDER_URL` | Subagent 地址 | http://localhost:8101 | — |

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

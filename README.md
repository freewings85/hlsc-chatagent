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

### 已知限制

- **Interrupt 依赖 Temporal**：未配置 Temporal 时 ask_user 工具不可用
- **Interrupt 期间重启会丢失当前请求的消息**：持久化发生在请求结束时（agent loop 退出后），如果 ask_user interrupt 等待期间后端重启，本次请求的所有消息（用户输入 + LLM 回复 + 工具调用）不会被写入文件。重启后前端 reply interrupt 会收到 410，用户需重新发送消息。之前的历史消息不受影响。

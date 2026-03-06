# Agent 主 Loop 架构设计蓝方审查报告

> 审查日期：2026-03-06
> 审查工具：Codex (Plan Agent)

## 1. 完整性

### [P0] Attachment 注入时机缺少 tool 执行后的重算

Claude Code 的 attachment 在两个时机计算：用户消息到达时（三组全算）和 tool 执行后（跳过第一组，二三组重算）。设计文档中 `AttachmentCollector.refresh(run)` 只出现在 `ModelRequestNode` 分支内，表面上等价（tool 执行完后下一个 node 就是 ModelRequestNode），但设计文档没有明确说明：refresh 此时应该感知到"刚执行了 tool"这个上下文，并根据 tool 的副作用（如文件变更）动态调整 attachment 内容。

**建议**：在设计文档中明确 `AttachmentCollector.refresh()` 的两种模式（首次 vs tool 后重算），或者在 `CallToolsNode` 之后显式标注"收集 tool 副作用信息供下一轮 attachment 使用"。

### [P1] 缺少错误事件的发射

设计文档的完整流程中没有出现 `emitter.emit(error)` 的环节。EventType 枚举中定义了 ERROR 类型，但 loop 流程中没有任何异常捕获和错误事件发射的描述。

### [P1] 缺少 agent.md 的注入方式说明

Claude Code 的 CLAUDE.md 是作为 messages[0] 的 user 消息临时注入的，不是写进 system prompt。设计文档没有明确选择哪种方式。

### [P1] 缺少 Compact 后的上下文恢复机制

Claude Code 在 Full LLM Compact 之后会恢复关键上下文：最近读过的文件（最多 5 个）、Todo 列表、Plan 文件、已激活的 Skills 等。设计文档只描述了"压缩"的部分，没有提到压缩后如何恢复关键上下文。

### [P2] Memory Layer 2（auto-memory）的写入触发条件不明确

Claude Code 的 auto-memory 是 agent 通过 Write/Edit 工具主动更新的，而非 loop 结束后自动提取。设计文档没有说明 `save()` 的具体逻辑。

## 2. 正确性

### [P0] Compact 和 Attachment 的执行顺序有依赖问题

Compact 可能删除/替换消息，而 Attachment 需要合并到最近的 user 消息中。Claude Code 的顺序：先压缩稳定消息结构，再注入动态 attachment。设计文档的顺序（4→5）是正确的，但没有说明 attachment 合并的具体实现方式。

### [P0] summary.md 读写竞态

步骤 6 后台写 summary.md，步骤 4（下一轮）读 summary.md。后台提取未完成时可能读到旧版本或写入一半的内容。

**建议**：
1. 后台提取完成后设置标志（如 `self._summary_ready = True`），Compactor 检查该标志
2. 或者用 `asyncio.Lock` 保护读写
3. 或者 summary.md 采用"写新文件 + 原子重命名"策略

## 3. 一致性

### [P0] EventEmitter 和 EventHandler 的对接断裂

谁从 EventEmitter 的 queue 取事件并交给 EventHandler？TaskWorker 的 `_worker_loop` 是从 `task_queue.get_ready_task()` 取 task，不是从 emitter 的 queue 取 event。需要一个消费协程：

```python
async def _consume_events(emitter_queue, handler):
    while True:
        event = await emitter_queue.get()
        if event is None:
            break
        await handler.handle(event)
```

并在 `_execute()` 中用 `asyncio.gather(run_agent_loop(...), _consume_events(...))` 并行运行。

### [P1] FileSystemBackend 的路径格式不一致

Backend docstring 用 `/sessions/xxx/`，设计文档用 `data/{user_id}/sessions/`。谁负责拼接 `data/{user_id}/` 前缀？

### [P1] create_agent 中 system_prompt 是静态字符串参数

Pydantic AI 的 Agent 构造后 system_prompt 是固定的。但 PromptBuilder 需要根据 task 动态组装。需要使用 `@agent.system_prompt` 装饰器方式。

## 4. 可行性

### [P0] Pydantic AI 的 iter/next 模型不支持直接修改中间消息

设计假设可以在 ModelRequestNode 之前修改 run 内部的消息历史，但 AgentRun 没有公开 API 允许在运行中修改消息历史。

可能的解决路径：
1. `history_processors`：Pydantic AI 提供的消息预处理钩子，在每次 LLM 调用前对消息做变换
2. 直接操作内部属性：不推荐

**建议**：先写 PoC 验证 history_processors 是否能满足 compact 和 attachment 注入需求。

### [P1] 并发 LLM 调用的资源竞争

后台 session memory 提取的 LLM 调用可能触发 rate limit，影响主循环的关键路径调用。

## 5. 遗漏风险

### [P0] emitter.close() 不保证被调用

如果循环内部抛出未捕获异常，emitter.close() 不会被调用。SSE 客户端会永远挂起。必须放在 try/finally 块中。

### [P0] 多 worker 同时操作同一 user 的 memory.md

SessionRequestTaskQueue 保证同一 session 串行，但同一 user 的不同 session 可以并行。memory.md 是 user 级别的，可能被并发写入导致数据丢失。

**建议**：
1. 对 memory.md 的写入加 user 级别的锁
2. 或者使用 append-only 模式
3. 或者增加 user 级别的串行控制

### [P1] 没有任何超时机制

没有 LLM 调用超时、tool 执行超时、整体 session 超时的控制。

### [P1] TaskWorker._execute() 的异常处理不发送错误事件

异常只做了 logger.exception，客户端不会收到错误通知。

## 总体评价

设计思路清晰，分层架构合理。但存在 **6 个 P0 问题**：

1. Pydantic AI iter/next 是否支持运行中修改消息历史（可行性根基）
2. EventEmitter 到 EventHandler 的对接断裂
3. summary.md 读写竞态
4. emitter.close() 不保证被调用
5. user 级别 memory.md 并发写入
6. Attachment 的 tool 后重算未明确

### 建议的下一步

1. 先做 Pydantic AI 可行性 PoC（history_processors 能否实现 compact + attachment 注入）
2. 补完 Emitter-Handler 对接
3. 增加 user 级锁机制
4. 补充异常处理和超时控制

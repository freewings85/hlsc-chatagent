# Codex Review Round 2 — 2026-03-06

commit: (post-fix, main branch)
model: claude-opus-4-6 (蓝方审核员)

## 上轮问题修复验证

### P1 重复 ready 调度 — 已修复

`_ready_set` 在 `try_enqueue()`, `enqueue()`, `get_ready_task()`, `release()` 四处均正确维护。`enqueue()` 的 `sid not in self._ready_set` 检查有效防止重复放入。

### P2 _task_index 内存泄漏 — 已修复

`release()` 接受 `task_id` 参数并 pop 索引；`get_ready_task()` 中跳过 cancelled 任务时也清理索引。

### P0 Emitter-Handler 对接断裂 — 部分修复

`task_worker.py:_execute()` 中已写出 `_consume_events()` 消费协程和 `asyncio.gather()` 并行模式，但整段代码仍在 `# TODO` 注释中（第 78-85 行是 pass），实际未执行。严格来说"对接"存在于代码中但不生效。考虑到当前阶段是骨架 + TODO，可以接受，但需要明确标注。

### P0 emitter.close() 不保证被调用 — 已修复

`loop.py` 中 try/finally 保证 `emitter.close()` 始终执行。

### P0 手动消息操作可行性 — 已验证

设计文档新增 "P0-1 验证结论" 章节，记录了 PoC 验证结果和 tool_use/tool_result 配对约束。

---

## 本轮新发现

### [P1-1] task_worker.py — _execute() 中 emitter.close() 和 handler.close() 双重关闭语义冲突

**文件**: `src/engine/task_worker.py:77-96` + `src/agent/loop.py:92-97`

`run_agent_loop()` 的 finally 块调用 `emitter.close()`（放 None 哨兵），而 `_execute()` 的 finally 块调用 `handler.close()`（关闭 sinker）。当 TODO 代码启用后，`asyncio.gather()` 中 `run_agent_loop()` 异常会导致：

1. `run_agent_loop` 的 finally 放入 None 哨兵
2. `_consume_events` 收到 None 后退出
3. `_execute` 的 finally 调用 `handler.close()`

这个顺序在正常情况下是对的。但如果 `_consume_events` 本身抛异常（比如 `handler.handle()` 失败），`asyncio.gather()` 会取消另一个协程（`run_agent_loop`），此时 `run_agent_loop` 被 CancelledError 打断，其 finally 中的 `emitter.close()` 会执行，但 `_consume_events` 已经退出了，None 哨兵无人消费——这倒不是大问题因为 queue 会被 GC，但 `handler.close()` 可能在 `handler.handle()` 异常后再次调用 sinker.close()，需要确保 sinker.close() 是幂等的。

**建议**: 在 `EventSinker` 协议文档或 `EventHandler.close()` 中明确 close 必须幂等。

### [P1-2] task_queue.py — cancel() 不清理 _ready_set，可能导致空队列 session 残留在 ready

**文件**: `src/engine/task_queue.py:58-70`

场景：
1. session A enqueue 一个 task，sid 被放入 `_ready_set` 和 `_ready` 队列
2. 在 worker 取走之前，调用 `cancel(task_id)` 移除该 task
3. `_session_queues[sid]` 变为空，但 `_ready_set` 中仍有 sid，`_ready` 队列中仍有 sid
4. worker 从 `_ready.get()` 取出 sid，发现 `_session_queues[sid]` 为空，continue 跳过——功能上不会出错
5. 但如果随后没有新任务，`_session_queues` 中残留了一个空 deque（defaultdict 创建的），且 `_ready_set` 在 `get_ready_task` 的 continue 分支已 discard——最终一致

**结论**: 功能正确，但 cancel 后 `_session_queues` 会残留空 deque。长期运行中大量不同 session 被 cancel 会导致空 deque 累积。建议 cancel 后检查队列为空时 del 掉。

### [P1-3] task_queue.py — release() 中 del defaultdict 条目的 KeyError 风险

**文件**: `src/engine/task_queue.py:85`

```python
del self._session_queues[session_id]
```

`_session_queues` 是 `defaultdict(deque)`。如果 `release()` 被调用两次（虽然不应该），第二次 `self._session_queues[session_id]` 会因 defaultdict 自动创建一个空 deque，然后第 79 行检查为空，走到第 85 行 del——不会 KeyError 但会创建再删除，是无害的。

但更重要的是：如果在 `release()` 执行到第 79 行之前，另一个协程刚好 `enqueue()` 了同一个 session 的新任务，那么 `release()` 第 79 行发现队列非空，会放入 ready。这是正确行为（asyncio 单线程，不会真正并发），但值得在注释中说明 asyncio 单线程保证。

### [P1-4] test_skeleton.py — test_emitter_closed_on_exception 未真正测试异常路径

**文件**: `tests/test_skeleton.py:191-206`

测试名为 `test_emitter_closed_on_exception`，但注释承认 "使用一个会导致异常的 model 不太好控制"，实际走的是正常路径。这个测试与 `test_simple_text_response` 功能重复，没有覆盖异常场景。

**建议**: 使用一个抛异常的 FunctionModel 回调函数，配合 `pytest.raises` 验证异常被传播且 emitter 仍然关闭：

```python
def mock_error_model(messages, info):
    raise RuntimeError("LLM error")

async def test_emitter_closed_on_exception(self):
    model = FunctionModel(mock_error_model)
    agent = create_agent(model=model)
    ...
    with pytest.raises(RuntimeError):
        await run_agent_loop(emitter, task, agent, deps)
    sentinel = await event_queue.get()
    assert sentinel is None
```

### [P2-1] task_queue.py — try_enqueue() 和 enqueue() 的不对称设计

**文件**: `src/engine/task_queue.py:32-56`

`try_enqueue()` 用 `put_nowait()` 是同步的，`enqueue()` 用 `await self._ready.put()` 是异步的。由于 `asyncio.Queue()` 默认无界，`put_nowait()` 永远不会抛 `QueueFull`，两者行为等价。但如果将来 `_ready` 改为有界队列，`try_enqueue` 会静默丢失 ready 信号。建议统一为 `put_nowait`（因为 ready 队列语义上应该无界）或添加注释说明。

### [P2-2] task_worker.py — worker_id 未传入 logger

**文件**: `src/engine/task_worker.py:89`

```python
logger.exception("Worker %d failed on task %s", 0, task.task_id)
```

硬编码 `0` 而非实际 `worker_id`。`_worker_loop` 接收 `worker_id` 参数但 `_execute` 不接收。

**建议**: 将 `worker_id` 传入 `_execute()` 或在 `_worker_loop` 中做异常日志。

### [P2-3] loop.py — cancelled 检查粒度不足

**文件**: `src/agent/loop.py:70-71`

`task.cancelled` 只在循环顶部检查。如果 LLM 调用耗时很长（步骤 7），在 LLM 返回之前 cancel 不会生效，需要等到下一次循环迭代。这是设计文档中提到的 "正在执行的靠 Agent Loop 检查"，但粒度较粗。

**建议**: 在 `node = await run.next(node)` 之后再检查一次 `task.cancelled`，减少不必要的后续处理。

### [P2-4] 设计文档 — 流程图与代码的步骤编号不完全对应

**文件**: `doc/agent主loop设计.md` vs `src/agent/loop.py`

设计文档流程图列出步骤 1-11（含步骤 10 `emitter.emit(chat_request_end)` 和步骤 11 `emitter.close()`），但代码 `loop.py` 的 TODO 注释只标注到步骤 9，且步骤 10/11 不在 TODO 中而是隐式存在于 finally 块。建议在代码中补齐步骤 10 的 TODO 注释。

---

## 总结

| 级别 | 数量 | 说明 |
|------|------|------|
| P0 | 0 | 上轮 P0 问题已修复或验证 |
| P1 | 4 | sinker 幂等性约定、cancel 残留清理、release 并发注释、测试未覆盖异常路径 |
| P2 | 4 | enqueue 不对称、worker_id 硬编码、cancelled 检查粒度、文档步骤编号 |

**整体评价**: 上轮的核心问题（重复调度、内存泄漏、emitter-handler 对接、异常安全）均已得到有效修复或验证。代码质量明显提升。本轮未发现新的 P0 阻塞问题。P1 问题集中在边界条件和测试覆盖度，建议在后续迭代中处理。骨架阶段的 TODO 标注清晰，与设计文档基本一致。

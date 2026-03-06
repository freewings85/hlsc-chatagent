# Codex Review — 2026-03-06

commit: af0eb2c (feat: Producer → Handler → Sinker 事件架构 + Engine 任务队列)
model: gpt-5.3-codex

## P1（严重）- 同 session 可能被并发执行

文件: `src/engine/task_queue.py:47-49`

当同一个 session 连续 enqueue 多次，在 worker 还没取走第一个任务前，`_ready` 队列会被重复 push 同一个 sid。两个 worker 可能同时 pop 到同一个 session 的任务，破坏了单 session 串行的保证。

修复方向：enqueue 时检查 sid 是否已经在 `_ready` 或 `_executing` 中，避免重复放入。

## P2（严重）- _task_index 内存泄漏

文件: `src/engine/task_queue.py:84-88`

`_task_index` 只在 cancelled 分支清理，正常完成的 task 永远不会被移除。长期运行内存持续增长，且 `cancel()` 会对已完成的旧任务误操作返回 success。

修复方向：在 `release()` 或 `get_ready_task()` 返回 task 时清理对应的 `_task_index` 条目。

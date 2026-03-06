# Code Review Issues — Codex Adversarial Round 1

## Actionable Issues (to fix)

### Issue 2: [High] HistoryMessageLoader.append 在后端异常时可能删掉历史并静默失败
- 位置: src/agent/message/history_message_loader.py:153
- 问题: `adownload_files()` 失败时 existing="" 但仍执行 adelete(path)，导致旧数据丢失
- 修复: 读取失败时不删除旧文件

### Issue 3: [High] HistoryMessageLoader.save 忽略删除/写入失败
- 位置: src/agent/message/history_message_loader.py:124
- 问题: adelete()/awrite() 结果未校验
- 修复: 检查后端返回值

### Issue 4: [Medium] EventEmitter emit/close 竞态
- 位置: src/event/event_emitter.py:17
- 问题: emit() 和 close() 之间可能有竞态（asyncio context switch 点在 await queue.put）
- 修复: 用 asyncio.Lock 序列化

### Issue 8: [Medium] HistoryMessageLoader 未测试后端失败分支
- 位置: tests/agent/message/test_history_message_loader.py
- 修复: 添加 mock backend 失败测试

## Dismissed Issues

### Issue 1: TaskWorker._execute() is a stub
- 已知设计：pyproject.toml 中 coverage 配置排除了 task_worker

### Issue 5: max_iterations=0 可能执行一轮
- 验证为 false positive：实测 max_iterations=0 不产生 TEXT 事件

### Issue 6: "并发"队列测试实际是串行
- try_enqueue 是同步方法，无 await 点，无真正竞态可能。串行测试即可验证互斥逻辑。

### Issue 7: 缺少 TaskWorker 测试
- 已知：stub 模块不需要测试

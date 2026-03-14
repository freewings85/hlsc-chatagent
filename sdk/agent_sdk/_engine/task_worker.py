"""TaskWorker：worker pool，从队列取任务驱动执行"""

from __future__ import annotations

import asyncio
import logging

from agent_sdk._common.session_request_task import SessionRequestTask
from agent_sdk._engine.task_queue import SessionRequestTaskQueue
from agent_sdk._event.event_handler import EventHandler

logger: logging.Logger = logging.getLogger(__name__)


class TaskWorker:
    """Worker pool：从 SessionRequestTaskQueue 取任务，驱动 Agent 执行。"""

    def __init__(
        self,
        task_queue: SessionRequestTaskQueue,
        max_workers: int = 10,
    ) -> None:
        self._task_queue: SessionRequestTaskQueue = task_queue
        self._max_workers: int = max_workers
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """启动 worker pool。随 server lifespan 调用。"""
        for i in range(self._max_workers):
            worker: asyncio.Task[None] = asyncio.create_task(
                self._worker_loop(i),
                name=f"task-worker-{i}",
            )
            self._workers.append(worker)
        logger.info("TaskWorker started with %d workers", self._max_workers)

    async def stop(self) -> None:
        """停止 worker pool。"""
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("TaskWorker stopped")

    async def _worker_loop(self, worker_id: int) -> None:
        """单个 worker 的主循环：取任务 → 执行 → 释放。"""
        while True:
            task: SessionRequestTask = await self._task_queue.get_ready_task()
            try:
                await self._execute(task)
            finally:
                self._task_queue.release(task.session_id, task.task_id)

    async def _execute(self, task: SessionRequestTask) -> None:
        """执行一个任务：驱动 Agent Loop → Handler → Sinker。

        生产-消费并行模式：
        - 生产者：run_agent_loop() 通过 emitter 往 queue 放事件
        - 消费者：_consume_events() 从 queue 取事件交给 handler
        - 两者通过 asyncio.gather() 并行运行
        """
        from agent_sdk._event.event_emitter import EventEmitter
        from agent_sdk._event.event_model import EventModel

        event_queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter: EventEmitter = EventEmitter(event_queue)
        handler: EventHandler = EventHandler(task.sinker)

        async def _consume_events() -> None:
            """从 emitter 的 queue 取事件，派发到 handler。"""
            while True:
                event: EventModel | None = await event_queue.get()
                if event is None:
                    break
                await handler.handle(event)

        from agent_sdk._event.event_model import EventModel
        from agent_sdk._event.event_type import EventType

        # 使用 lazy Agent（与 _server/app.py 共享逻辑）
        from agent_sdk._server.app import _get_agent

        agent = _get_agent()

        try:
            await asyncio.gather(
                agent.run(
                    message=task.message,
                    user_id=task.user_id,
                    session_id=task.session_id,
                    emitter=emitter,
                ),
                _consume_events(),
            )
        except Exception:
            logger.exception(
                "Worker failed on task %s",
                task.task_id,
            )
            # 发送错误事件通知客户端
            error_event: EventModel = EventModel(
                session_id=task.session_id,
                request_id=task.request_id,
                type=EventType.ERROR,
                data={"error": "Agent 执行异常"},
            )
            await handler.handle(error_event)
        finally:
            await handler.close()

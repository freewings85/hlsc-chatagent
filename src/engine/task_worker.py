"""TaskWorker：worker pool，从队列取任务驱动执行"""

from __future__ import annotations

import asyncio
import logging

from src.common.session_request_task import SessionRequestTask
from src.engine.task_queue import SessionRequestTaskQueue
from src.event.event_handler import EventHandler

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
            except Exception:
                logger.exception(
                    "Worker %d failed on task %s", worker_id, task.task_id
                )
            finally:
                self._task_queue.release(task.session_id)

    async def _execute(self, task: SessionRequestTask) -> None:
        """执行一个任务：驱动 Agent Loop → Handler → Sinker。"""
        handler: EventHandler = EventHandler(task.sinker)
        try:
            # TODO: 接入 Agent Loop，产出事件流
            # async for event in run_agent_stream(agent, task, deps):
            #     if task.cancelled:
            #         break
            #     await handler.handle(event)
            pass
        finally:
            await handler.close()

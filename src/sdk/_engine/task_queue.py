"""会话请求任务队列：全局并发可配置，单 session 串行"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from src.sdk._common.session_request_task import SessionRequestTask


class SessionRequestTaskQueue:
    """按 session_id 管理有界队列，控制并发和调度。"""

    def __init__(self, max_queue_per_session: int = 2) -> None:
        self._max_queue_per_session: int = max_queue_per_session

        # per-session 的任务队列
        self._session_queues: dict[str, deque[SessionRequestTask]] = defaultdict(deque)

        # 正在执行的 session 集合
        self._executing: set[str] = set()

        # ready 队列：有任务且当前没在执行的 session_id
        self._ready: asyncio.Queue[str] = asyncio.Queue()

        # 已在 ready 队列中的 session 集合（防止重复放入）
        self._ready_set: set[str] = set()

        # task_id → task 的索引，用于 cancel 查找
        self._task_index: dict[str, SessionRequestTask] = {}

    def try_enqueue(self, task: SessionRequestTask) -> bool:
        """SSE 用：队列必须为空且不在执行中才成功。"""
        sid: str = task.session_id
        if sid in self._executing or len(self._session_queues[sid]) > 0:
            return False
        self._session_queues[sid].append(task)
        self._task_index[task.task_id] = task
        if sid not in self._ready_set:
            self._ready_set.add(sid)
            self._ready.put_nowait(sid)
        return True

    async def enqueue(self, task: SessionRequestTask) -> bool:
        """异步用：队列没满就入队，满了返回 False。"""
        sid: str = task.session_id
        total: int = len(self._session_queues[sid]) + (1 if sid in self._executing else 0)
        if total >= self._max_queue_per_session:
            return False
        self._session_queues[sid].append(task)
        self._task_index[task.task_id] = task
        # 如果该 session 当前没在执行且不在 ready 队列中，放入 ready 队列
        if sid not in self._executing and sid not in self._ready_set:
            self._ready_set.add(sid)
            await self._ready.put(sid)
        return True

    def cancel(self, task_id: str) -> bool:
        """通过 task_id 取消任务。正在执行的设 cancelled=True，排队中的直接移除。"""
        task: SessionRequestTask | None = self._task_index.get(task_id)
        if task is None:
            return False
        sid: str = task.session_id
        # 如果在排队中，直接移除
        if task in self._session_queues[sid]:
            self._session_queues[sid].remove(task)
            del self._task_index[task_id]
        # 不管是否在排队，都设置 cancelled（正在执行的靠 Agent Loop 检查）
        task.cancelled = True
        return True

    def release(self, session_id: str, task_id: str | None = None) -> None:
        """执行完毕释放，清理索引，通知队列中下一个任务。"""
        self._executing.discard(session_id)
        # 清理已完成任务的索引
        if task_id is not None:
            self._task_index.pop(task_id, None)
        # 如果该 session 还有排队任务，重新放入 ready
        if self._session_queues[session_id]:
            if session_id not in self._ready_set:
                self._ready_set.add(session_id)
                self._ready.put_nowait(session_id)
        else:
            # 清理空队列
            del self._session_queues[session_id]

    async def get_ready_task(self) -> SessionRequestTask:
        """阻塞等待下一个可执行的任务。TaskWorker 调用。"""
        while True:
            sid: str = await self._ready.get()
            self._ready_set.discard(sid)
            if not self._session_queues[sid]:
                continue
            task: SessionRequestTask = self._session_queues[sid].popleft()
            if task.cancelled:
                self._task_index.pop(task.task_id, None)
                # 如果该 session 还有后续任务，重新放入 ready
                if self._session_queues[sid]:
                    if sid not in self._ready_set:
                        self._ready_set.add(sid)
                        await self._ready.put(sid)
                continue
            self._executing.add(sid)
            return task

    def try_get_ready_task(self) -> SessionRequestTask | None:
        """非阻塞获取下一个可执行的任务。队列为空时返回 None。"""
        while not self._ready.empty():
            try:
                sid = self._ready.get_nowait()
            except asyncio.QueueEmpty:
                return None
            self._ready_set.discard(sid)
            if not self._session_queues[sid]:
                continue
            task = self._session_queues[sid].popleft()
            if task.cancelled:
                self._task_index.pop(task.task_id, None)
                if self._session_queues[sid]:
                    if sid not in self._ready_set:
                        self._ready_set.add(sid)
                        self._ready.put_nowait(sid)
                continue
            self._executing.add(sid)
            return task
        return None

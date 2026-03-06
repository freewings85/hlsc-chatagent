"""SessionRequestTaskQueue 测试"""

import asyncio

import pytest

from src.common.session_request_task import SessionRequestTask
from src.engine.task_queue import SessionRequestTaskQueue
from tests.conftest import MockSinker


def _make_task(session_id: str = "s1", task_id: str | None = None) -> SessionRequestTask:
    sinker = MockSinker()
    task = SessionRequestTask(session_id=session_id, message="hi", user_id="u1", sinker=sinker)
    if task_id is not None:
        task.task_id = task_id
    return task


class TestTryEnqueue:

    def test_enqueue_empty_session(self) -> None:
        q = SessionRequestTaskQueue()
        task = _make_task()
        assert q.try_enqueue(task) is True

    def test_reject_when_executing(self) -> None:
        q = SessionRequestTaskQueue()
        t1 = _make_task()
        q.try_enqueue(t1)
        # 模拟取出执行
        q._executing.add("s1")
        q._session_queues["s1"].popleft()
        # 再入队应被拒绝
        t2 = _make_task()
        assert q.try_enqueue(t2) is False

    def test_reject_when_queued(self) -> None:
        q = SessionRequestTaskQueue()
        t1 = _make_task()
        q.try_enqueue(t1)
        t2 = _make_task()
        assert q.try_enqueue(t2) is False


class TestAsyncEnqueue:

    @pytest.mark.asyncio
    async def test_enqueue_success(self) -> None:
        q = SessionRequestTaskQueue(max_queue_per_session=2)
        t1 = _make_task()
        assert await q.enqueue(t1) is True

    @pytest.mark.asyncio
    async def test_enqueue_reject_full(self) -> None:
        q = SessionRequestTaskQueue(max_queue_per_session=1)
        t1 = _make_task()
        await q.enqueue(t1)
        t2 = _make_task()
        assert await q.enqueue(t2) is False

    @pytest.mark.asyncio
    async def test_enqueue_counts_executing(self) -> None:
        """正在执行的也算在 max_queue 里"""
        q = SessionRequestTaskQueue(max_queue_per_session=1)
        q._executing.add("s1")
        t1 = _make_task()
        assert await q.enqueue(t1) is False

    @pytest.mark.asyncio
    async def test_enqueue_no_duplicate_ready(self) -> None:
        """同 session 已在 ready 中不重复放入"""
        q = SessionRequestTaskQueue(max_queue_per_session=3)
        t1 = _make_task()
        await q.enqueue(t1)
        # s1 已在 ready_set 中
        assert "s1" in q._ready_set
        t2 = _make_task()
        await q.enqueue(t2)
        # ready_set 仍只有一个
        assert q._ready.qsize() == 1


class TestCancel:

    def test_cancel_queued_task(self) -> None:
        q = SessionRequestTaskQueue()
        task = _make_task(task_id="t1")
        q.try_enqueue(task)
        assert q.cancel("t1") is True
        assert task.cancelled is True
        # 已从队列移除
        assert task not in q._session_queues["s1"]

    def test_cancel_executing_task(self) -> None:
        q = SessionRequestTaskQueue()
        task = _make_task(task_id="t1")
        q._task_index["t1"] = task
        q._executing.add("s1")
        assert q.cancel("t1") is True
        assert task.cancelled is True

    def test_cancel_nonexistent(self) -> None:
        q = SessionRequestTaskQueue()
        assert q.cancel("nonexistent") is False


class TestRelease:

    def test_release_clears_executing(self) -> None:
        q = SessionRequestTaskQueue()
        q._executing.add("s1")
        q._task_index["t1"] = _make_task(task_id="t1")
        q.release("s1", "t1")
        assert "s1" not in q._executing
        assert "t1" not in q._task_index

    def test_release_with_pending_tasks(self) -> None:
        q = SessionRequestTaskQueue()
        q._executing.add("s1")
        t2 = _make_task()
        q._session_queues["s1"].append(t2)
        q.release("s1")
        # 应该把 s1 放回 ready
        assert "s1" in q._ready_set

    def test_release_cleans_empty_queue(self) -> None:
        q = SessionRequestTaskQueue()
        q._executing.add("s1")
        q._session_queues["s1"]  # 创建空 deque
        q.release("s1")
        assert "s1" not in q._session_queues


class TestGetReadyTask:

    @pytest.mark.asyncio
    async def test_get_ready_task(self) -> None:
        q = SessionRequestTaskQueue()
        task = _make_task(task_id="t1")
        q.try_enqueue(task)
        result = await q.get_ready_task()
        assert result is task
        assert "s1" in q._executing

    @pytest.mark.asyncio
    async def test_skip_cancelled_task(self) -> None:
        """已取消的任务跳过，取下一个"""
        q = SessionRequestTaskQueue(max_queue_per_session=3)
        t1 = _make_task(task_id="t1")
        t2 = _make_task(task_id="t2")
        await q.enqueue(t1)
        await q.enqueue(t2)
        t1.cancelled = True
        result = await q.get_ready_task()
        assert result is t2

    @pytest.mark.asyncio
    async def test_skip_empty_session(self) -> None:
        """session 队列为空时跳过"""
        q = SessionRequestTaskQueue()
        # 手动放一个 sid 到 ready 但不放任务
        await q._ready.put("empty_session")
        q._ready_set.add("empty_session")
        # 放一个真正有任务的
        task = _make_task(session_id="s2", task_id="t1")
        await q.enqueue(task)
        result = await q.get_ready_task()
        assert result is task

    @pytest.mark.asyncio
    async def test_cancelled_with_next_in_queue(self) -> None:
        """取消的任务后面还有排队任务，应重新放入 ready"""
        q = SessionRequestTaskQueue(max_queue_per_session=3)
        t1 = _make_task(task_id="t1")
        t2 = _make_task(task_id="t2")
        await q.enqueue(t1)
        await q.enqueue(t2)
        t1.cancelled = True
        result = await q.get_ready_task()
        assert result is t2

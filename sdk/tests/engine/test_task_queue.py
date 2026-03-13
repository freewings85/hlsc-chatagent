"""SessionRequestTaskQueue 测试"""

import asyncio

import pytest

from agent_sdk._common.session_request_task import SessionRequestTask
from agent_sdk._engine.task_queue import SessionRequestTaskQueue
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


class TestTaskQueueEdgeCases:
    """US-005: TaskQueue 并发控制与取消机制"""

    def test_concurrent_try_enqueue_mutual_exclusion(self) -> None:
        """同一 session 并发 try_enqueue 时只有一个成功"""
        q = SessionRequestTaskQueue()
        t1 = _make_task(task_id="t1")
        t2 = _make_task(task_id="t2")

        r1 = q.try_enqueue(t1)
        r2 = q.try_enqueue(t2)

        assert r1 is True
        assert r2 is False

    @pytest.mark.asyncio
    async def test_concurrent_async_enqueue_mutual_exclusion(self) -> None:
        """同一 session async enqueue，max=1 时只有一个成功"""
        q = SessionRequestTaskQueue(max_queue_per_session=1)
        t1 = _make_task(task_id="t1")
        t2 = _make_task(task_id="t2")

        r1 = await q.enqueue(t1)
        r2 = await q.enqueue(t2)

        assert r1 is True
        assert r2 is False

    def test_cancel_waiting_task_sets_cancelled(self) -> None:
        """cancel 正在等待的任务能正确设置 cancelled 标记"""
        q = SessionRequestTaskQueue(max_queue_per_session=3)
        t1 = _make_task(task_id="t1")
        q.try_enqueue(t1)

        assert t1.cancelled is False
        result = q.cancel("t1")
        assert result is True
        assert t1.cancelled is True

    def test_release_then_reenqueue(self) -> None:
        """release 后同一 session 可以再次 enqueue"""
        q = SessionRequestTaskQueue()
        t1 = _make_task(task_id="t1")
        q.try_enqueue(t1)

        # 模拟取出执行
        q._session_queues["s1"].popleft()
        q._executing.add("s1")

        # release
        q.release("s1", "t1")
        assert "s1" not in q._executing

        # 可以再次 enqueue
        t2 = _make_task(task_id="t2")
        result = q.try_enqueue(t2)
        assert result is True

    def test_try_get_ready_task_empty_returns_none(self) -> None:
        """try_get_ready_task 在队列为空时返回 None"""
        q = SessionRequestTaskQueue()
        result = q.try_get_ready_task()
        assert result is None

    def test_try_get_ready_task_returns_task(self) -> None:
        """try_get_ready_task 有任务时返回任务"""
        q = SessionRequestTaskQueue()
        t1 = _make_task(task_id="t1")
        q.try_enqueue(t1)

        result = q.try_get_ready_task()
        assert result is t1
        assert "s1" in q._executing


class TestTryGetReadyTaskEdgeCases:
    """US-004: try_get_ready_task 边界路径（task_queue.py 111-112, 115, 118-123）"""

    def test_skip_empty_session_in_ready(self) -> None:
        """ready 队列中有 session_id 但 session_queues 为空时跳过并返回 None（覆盖 114-115 行）"""
        q = SessionRequestTaskQueue()
        # 手动放 sid 到 ready 但不放任务
        q._ready.put_nowait("empty_session")
        q._ready_set.add("empty_session")

        result = q.try_get_ready_task()
        assert result is None

    def test_skip_cancelled_task_in_try_get(self) -> None:
        """try_get_ready_task 跳过已取消的任务（覆盖 117-119 行）"""
        q = SessionRequestTaskQueue()
        t1 = _make_task(task_id="t1")
        q.try_enqueue(t1)
        t1.cancelled = True

        result = q.try_get_ready_task()
        assert result is None

    def test_cancelled_with_next_in_try_get(self) -> None:
        """try_get_ready_task 跳过取消任务后还有后续任务时重新放入 ready（覆盖 118-123 行）"""
        q = SessionRequestTaskQueue(max_queue_per_session=3)
        t1 = _make_task(task_id="t1")
        t2 = _make_task(task_id="t2")
        q.try_enqueue(t1)
        # 手动加入 t2（try_enqueue 会拒绝，因为 t1 已在队列）
        q._session_queues["s1"].append(t2)
        q._task_index["t2"] = t2

        t1.cancelled = True

        result = q.try_get_ready_task()
        assert result is t2
        assert "s1" in q._executing

    def test_try_get_ready_task_queue_empty_race(self) -> None:
        """ready.empty() 返回 False 但 get_nowait() 抛出 QueueEmpty 时返回 None（覆盖 111-112 行）"""
        q = SessionRequestTaskQueue()

        # 模拟竞态：empty() 说不为空，但实际 get_nowait() 抛出 QueueEmpty
        q._ready.empty = lambda: False  # type: ignore[method-assign]
        q._ready.get_nowait = lambda: (_ for _ in ()).throw(asyncio.QueueEmpty())  # type: ignore[method-assign]

        result = q.try_get_ready_task()
        assert result is None

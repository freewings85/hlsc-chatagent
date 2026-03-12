"""Temporal interrupt 集成测试

需要 Temporal server 运行在 localhost:7233。
使用 pytest.mark.temporal 标记，CI 中可选跳过。
"""

import asyncio
import uuid

import pytest
from temporalio.client import Client

from src.sdk._agent.interrupt import (
    InterruptWorkflow,
    create_interrupt_worker,
    interrupt,
    resume,
)

TASK_QUEUE = "test-interrupt-queue"


def _unique_key(prefix: str = "test") -> str:
    """每次测试生成唯一 key，避免 Temporal workflow ID 冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def temporal_client():
    """连接到本地 Temporal server。"""
    try:
        client = await Client.connect("localhost:7233")
    except Exception:
        pytest.skip("Temporal server not available at localhost:7233")
    return client


@pytest.fixture
async def temporal_worker(temporal_client):
    """启动 interrupt worker（测试用 unsandboxed runner 避免 import path 校验问题）。"""
    from temporalio.worker import UnsandboxedWorkflowRunner
    from src.sdk._agent.interrupt import InterruptWorkflow
    from temporalio.worker import Worker
    worker = Worker(
        temporal_client,
        task_queue=TASK_QUEUE,
        workflows=[InterruptWorkflow],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )
    task = asyncio.create_task(worker.run())
    yield worker
    await worker.shutdown()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


class TestInterruptResume:
    """interrupt + resume 完整流程"""

    @pytest.mark.asyncio
    async def test_interrupt_then_resume(self, temporal_client, temporal_worker) -> None:
        """interrupt 等待，resume 唤醒，返回用户数据"""
        callback_called = False
        callback_interrupt_id = None

        async def my_callback(data: dict, interrupt_id: str) -> None:
            nonlocal callback_called, callback_interrupt_id
            callback_called = True
            callback_interrupt_id = interrupt_id

        # 在后台运行 interrupt（它会阻塞直到 resume）
        key = _unique_key("interrupt")

        async def do_interrupt():
            return await interrupt(
                temporal_client, key, my_callback,
                {"question": "确认？"},
                task_queue=TASK_QUEUE,
            )

        interrupt_task = asyncio.create_task(do_interrupt())

        # 等待 callback 执行完成
        for _ in range(50):
            await asyncio.sleep(0.1)
            if callback_called:
                break
        assert callback_called, "callback should have been called"
        assert callback_interrupt_id is not None

        # 发送 resume
        await resume(temporal_client, key, {"reply": "确认", "extra": "data"})

        # 等待 interrupt 返回
        result = await asyncio.wait_for(interrupt_task, timeout=5.0)

        assert result["reply"] == "确认"
        assert result["extra"] == "data"

    @pytest.mark.asyncio
    async def test_resume_before_callback_done_rejected(self, temporal_client, temporal_worker) -> None:
        """callback 未完成时 resume 应被拒绝"""
        key = _unique_key("reject")

        # 手动启动 workflow（不经过 interrupt 函数，模拟 callback 未完成）
        handle = await temporal_client.start_workflow(
            InterruptWorkflow.run,
            {"test": True},
            id=key,
            task_queue=TASK_QUEUE,
        )

        # 此时 status 应为 "pending"
        status = await handle.query(InterruptWorkflow.status)
        assert status == "pending"

        with pytest.raises(RuntimeError, match="尚未就绪"):
            await resume(temporal_client, key, {"reply": "too early"})

        # 清理：标记 callback done + resume
        await handle.signal(InterruptWorkflow.on_callback_done)
        await handle.signal(InterruptWorkflow.on_resume, {"reply": "cleanup"})
        await asyncio.wait_for(handle.result(), timeout=5.0)

    @pytest.mark.asyncio
    async def test_workflow_status_transitions(self, temporal_client, temporal_worker) -> None:
        """验证 workflow 状态转换：pending → waiting → resumed"""
        key = _unique_key("status")

        handle = await temporal_client.start_workflow(
            InterruptWorkflow.run,
            {"test": True},
            id=key,
            task_queue=TASK_QUEUE,
        )

        # pending
        status = await handle.query(InterruptWorkflow.status)
        assert status == "pending"

        # → waiting
        await handle.signal(InterruptWorkflow.on_callback_done)
        await asyncio.sleep(0.2)
        status = await handle.query(InterruptWorkflow.status)
        assert status == "waiting"

        # → resumed
        await handle.signal(InterruptWorkflow.on_resume, {"reply": "done"})
        result = await asyncio.wait_for(handle.result(), timeout=5.0)
        assert result["reply"] == "done"

    @pytest.mark.asyncio
    async def test_multiple_interrupts_different_keys(self, temporal_client, temporal_worker) -> None:
        """多个 interrupt 使用不同 key，互不干扰"""
        results = {}

        async def callback(data, interrupt_id):
            pass

        async def do_interrupt(k, question):
            r = await interrupt(
                temporal_client, k, callback,
                {"q": question},
                task_queue=TASK_QUEUE,
            )
            results[k] = r

        k1 = _unique_key("multi-1")
        k2 = _unique_key("multi-2")

        t1 = asyncio.create_task(do_interrupt(k1, "Q1"))
        t2 = asyncio.create_task(do_interrupt(k2, "Q2"))

        await asyncio.sleep(1)

        await resume(temporal_client, k2, {"reply": "A2"})
        await resume(temporal_client, k1, {"reply": "A1"})

        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=5.0)

        assert results[k1]["reply"] == "A1"
        assert results[k2]["reply"] == "A2"

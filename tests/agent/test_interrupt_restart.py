"""进程重启后 interrupt 行为测试。

验证：
1. interrupt workflow 在 Temporal 中仍然存在（持久化）
2. resume 发送到已存在但无 agent loop 消费的 workflow → workflow 完成
3. 但 agent loop 已死，不会处理结果（用户会收到 HTTP 错误是前端行为，不在此测试）

需要 Temporal server 运行在 localhost:7233。
"""

import asyncio
import uuid

import pytest
from temporalio.client import Client, WorkflowExecutionStatus

from src.agent.interrupt import (
    InterruptWorkflow,
    create_interrupt_worker,
    interrupt,
    resume,
)

TASK_QUEUE = "test-restart-queue"


def _unique_key(prefix: str = "restart") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def temporal_client():
    try:
        client = await Client.connect("localhost:7233")
    except Exception:
        pytest.skip("Temporal server not available at localhost:7233")
    return client


@pytest.fixture
async def temporal_worker(temporal_client):
    worker = create_interrupt_worker(temporal_client, task_queue=TASK_QUEUE)
    task = asyncio.create_task(worker.run())
    yield worker
    await worker.shutdown()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


class TestInterruptProcessRestart:
    """模拟进程重启场景"""

    @pytest.mark.asyncio
    async def test_workflow_survives_after_interrupt_caller_dies(
        self, temporal_client, temporal_worker,
    ) -> None:
        """interrupt 调用方消失后，workflow 仍在 Temporal 中运行。

        模拟场景：
        1. 启动 interrupt（agent loop 中）
        2. 取消 interrupt task（模拟进程崩溃）
        3. workflow 仍在 Temporal 中 RUNNING
        4. resume 仍可发送
        5. workflow 正常完成
        """
        key = _unique_key("survive")

        callback_done = False

        async def my_callback(data: dict, interrupt_id: str) -> None:
            nonlocal callback_done
            callback_done = True

        # 启动 interrupt 但不等待结果
        interrupt_task = asyncio.create_task(
            interrupt(
                temporal_client, key, my_callback,
                {"question": "还在吗？"},
                task_queue=TASK_QUEUE,
            )
        )

        # 等待 callback 完成
        for _ in range(50):
            await asyncio.sleep(0.1)
            if callback_done:
                break
        assert callback_done

        # 模拟进程崩溃：取消等待 interrupt 的 coroutine
        interrupt_task.cancel()
        try:
            await interrupt_task
        except asyncio.CancelledError:
            pass

        # workflow 应仍在 Temporal 中运行
        handle = temporal_client.get_workflow_handle(key)
        desc = await handle.describe()
        assert desc.status == WorkflowExecutionStatus.RUNNING

        status = await handle.query(InterruptWorkflow.status)
        assert status == "waiting"  # callback done, waiting for resume

        # resume 仍能成功发送
        await resume(temporal_client, key, {"reply": "我回来了"})

        # workflow 正常完成
        result = await asyncio.wait_for(handle.result(), timeout=5.0)
        assert result["reply"] == "我回来了"

    @pytest.mark.asyncio
    async def test_new_process_can_query_workflow_status(
        self, temporal_client, temporal_worker,
    ) -> None:
        """新进程可以查询 workflow 状态（模拟重启后的诊断）。"""
        key = _unique_key("query")

        # 手动启动 workflow（模拟上一个进程的 interrupt）
        handle = await temporal_client.start_workflow(
            InterruptWorkflow.run,
            {"question": "测试"},
            id=key,
            task_queue=TASK_QUEUE,
        )

        # 新进程通过 key 查询状态
        new_handle = temporal_client.get_workflow_handle(key)
        desc = await new_handle.describe()
        assert desc.status == WorkflowExecutionStatus.RUNNING

        status = await new_handle.query(InterruptWorkflow.status)
        assert status == "pending"

        # 清理
        await handle.signal(InterruptWorkflow.on_callback_done)
        await handle.signal(InterruptWorkflow.on_resume, {"reply": "cleanup"})
        await asyncio.wait_for(handle.result(), timeout=5.0)

    @pytest.mark.asyncio
    async def test_reconnect_to_existing_workflow(
        self, temporal_client, temporal_worker,
    ) -> None:
        """interrupt() 函数重连到已存在的 workflow（模拟新进程恢复）。

        场景：
        1. 进程 A 启动 interrupt → workflow 创建，callback done，waiting
        2. 进程 A 崩溃
        3. 进程 B 用同一个 key 调 interrupt() → 应该重连到已有 workflow
        4. 进程 B 的 callback 不应被重复调用（已经 done）
        5. resume 后 interrupt() 返回结果
        """
        key = _unique_key("reconnect")

        callback_count = 0

        async def counting_callback(data: dict, interrupt_id: str) -> None:
            nonlocal callback_count
            callback_count += 1

        # 进程 A：启动 interrupt
        task_a = asyncio.create_task(
            interrupt(
                temporal_client, key, counting_callback,
                {"question": "进程A"},
                task_queue=TASK_QUEUE,
            )
        )

        # 等待进入 waiting
        for _ in range(50):
            await asyncio.sleep(0.1)
            if callback_count >= 1:
                break
        assert callback_count == 1

        # 进程 A 崩溃
        task_a.cancel()
        try:
            await task_a
        except asyncio.CancelledError:
            pass

        # 进程 B：用同一个 key 再次调 interrupt
        # callback 不应再被调（status 已经是 waiting）
        task_b = asyncio.create_task(
            interrupt(
                temporal_client, key, counting_callback,
                {"question": "进程B"},
                task_queue=TASK_QUEUE,
            )
        )

        await asyncio.sleep(0.5)
        # callback 不应该再次被调用
        assert callback_count == 1, f"callback 不应重复调用，实际次数: {callback_count}"

        # resume
        await resume(temporal_client, key, {"reply": "恢复了"})

        result = await asyncio.wait_for(task_b, timeout=5.0)
        assert result["reply"] == "恢复了"

    @pytest.mark.asyncio
    async def test_interrupt_reply_to_nonexistent_key_fails(
        self, temporal_client, temporal_worker,
    ) -> None:
        """resume 不存在的 key 应报错（前端发给错误服务器时的行为）。"""
        key = _unique_key("nonexistent")

        with pytest.raises(Exception):
            await resume(temporal_client, key, {"reply": "没有这个 workflow"})

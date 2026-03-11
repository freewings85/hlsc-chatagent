"""通用 interrupt/resume 抽象层（基于 Temporal Workflow）。

发起方（agent tool 内部）:
    response = await interrupt(client, key, callback, data)

触发方（HTTP endpoint / 任意进程）:
    await resume(client, key, {"approved": True})

设计要点：
- interrupt() 在 agent loop 协程中 await，协程挂起但不阻塞事件循环
- callback 用于发送 interrupt 事件给前端（带 interrupt_id）
- Temporal Workflow 保证 interrupt 状态持久化（进程重启后 workflow 仍在）
- 但 agent loop 协程在内存中，进程重启后丢失，resume 会返回报错
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Callable, Coroutine

from temporalio import workflow
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

# callback 签名：async def fn(data: dict, interrupt_id: str) -> None
InterruptCallback = Callable[[dict[str, Any], str], Coroutine[Any, Any, None]]


@workflow.defn
class InterruptWorkflow:
    """纯等待 Workflow —— 不执行任何 Activity，只等 resume 信号。"""

    def __init__(self) -> None:
        self._response: dict[str, Any] | None = None
        self._callback_done: bool = False

    @workflow.signal
    async def on_resume(self, data: dict[str, Any]) -> None:
        self._response = data

    @workflow.signal
    async def on_callback_done(self) -> None:
        self._callback_done = True

    @workflow.query
    def status(self) -> str:
        if self._response is not None:
            return "resumed"
        if self._callback_done:
            return "waiting"
        return "pending"

    @workflow.run
    async def run(self, data: dict[str, Any]) -> dict[str, Any]:
        await workflow.wait_condition(lambda: self._callback_done)
        await workflow.wait_condition(lambda: self._response is not None)
        return self._response  # type: ignore[return-value]


async def interrupt(
    client: Client | None,
    key: str,
    callback: InterruptCallback,
    data: dict[str, Any],
    *,
    task_queue: str = "interrupt-queue",
    task_timeout: timedelta = timedelta(seconds=10),
) -> dict[str, Any]:
    """发起一个 interrupt 调用，阻塞直到用户 resume。

    Args:
        client: Temporal client（None 时直接报错）
        key: 唯一标识（建议用 session_id + 序号）
        callback: 幂等 async 函数，签名 (data, interrupt_id) -> None
        data: 传给 callback 的业务数据
        task_queue: Temporal task queue 名称
        task_timeout: Workflow task 超时

    Returns:
        用户通过 resume 传回的数据
    """
    if client is None:
        raise RuntimeError("interrupt 需要 Temporal，请设置 TEMPORAL_ENABLED=true")

    handle = None

    # 尝试获取已存在的 Workflow（重连场景）
    try:
        handle = client.get_workflow_handle(key)
        desc = await handle.describe()

        if desc.status == WorkflowExecutionStatus.RUNNING:
            status = await handle.query(InterruptWorkflow.status)
            interrupt_id = desc.run_id

            if status == "waiting":
                return await handle.result()

            if status == "pending":
                await callback(data, interrupt_id)
                await handle.signal(InterruptWorkflow.on_callback_done)
                return await handle.result()

        if desc.status == WorkflowExecutionStatus.COMPLETED:
            return await handle.result()

        handle = None
    except Exception:
        handle = None

    # 首次调用
    handle = await client.start_workflow(
        InterruptWorkflow.run,
        data,
        id=key,
        task_queue=task_queue,
        task_timeout=task_timeout,
    )

    interrupt_id = handle.result_run_id
    await callback(data, interrupt_id)
    await handle.signal(InterruptWorkflow.on_callback_done)

    return await handle.result()


async def resume(client: Client, key: str, data: dict[str, Any]) -> None:
    """恢复一个等待中的 interrupt。

    Args:
        client: Temporal client
        key: interrupt 时使用的同一个 key
        data: 传回给发起方的数据
    """
    handle = client.get_workflow_handle(key)

    status = await handle.query(InterruptWorkflow.status)
    if status == "pending":
        raise RuntimeError(f"Interrupt '{key}' 尚未就绪（callback 未完成），不能 resume")

    await handle.signal(InterruptWorkflow.on_resume, data)


def create_interrupt_worker(
    client: Client,
    *,
    task_queue: str = "interrupt-queue",
) -> Worker:
    """创建 interrupt Worker（只处理 Workflow，无状态）。"""
    is_debugging = "debugpy" in sys.modules
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[InterruptWorkflow],
        **({"workflow_runner": UnsandboxedWorkflowRunner()} if is_debugging else {}),
    )

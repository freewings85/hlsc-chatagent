"""通用 interrupt/resume 抽象层。

两种模式（由 TEMPORAL_ENABLED 决定，运行时不可切换）：

1. TEMPORAL_ENABLED=true → Temporal Workflow 模式
   - interrupt 状态持久化，支持进程重启后 workflow 仍在
   - 必须连接 Temporal server，连接失败直接报错（不降级）

2. TEMPORAL_ENABLED=false → 内存模式
   - asyncio.Event 实现等待/恢复，纯单进程
   - 进程重启后所有 interrupt 丢失（与 Temporal 模式行为一致：agent loop 也在内存中）
   - 开发、测试、不需要持久化的场景

发起方（agent tool 内部）:
    response = await interrupt(client, key, callback, data)

触发方（HTTP endpoint / 任意进程）:
    await resume(client, key, {"approved": True})

    # 内存模式下 client 可传 None：
    await resume_memory(key, {"approved": True})
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any, Callable, Coroutine

# callback 签名：async def fn(data: dict, interrupt_id: str) -> None
InterruptCallback = Callable[[dict[str, Any], str], Coroutine[Any, Any, None]]

# 当前进程中活跃的 interrupt key 集合（内存态，重启后为空）
_active_interrupt_keys: set[str] = set()

# 内存模式 interrupt 等待超时（秒），超时后抛 asyncio.TimeoutError
_MEMORY_INTERRUPT_TIMEOUT: float = float(
    __import__("os").getenv("INTERRUPT_TIMEOUT_SECONDS", "300")  # 默认 5 分钟
)

# ── 内存模式状态 ──
# key → asyncio.Event（resume 时 set）
_memory_events: dict[str, asyncio.Event] = {}
# key → 用户回复数据
_memory_responses: dict[str, dict[str, Any]] = {}


def is_interrupt_active(key: str) -> bool:
    """检查 interrupt key 是否在当前进程中活跃。"""
    return key in _active_interrupt_keys


# ═══════════════════════════════════════════════
#  内存模式
# ═══════════════════════════════════════════════

async def _interrupt_memory(
    key: str,
    callback: InterruptCallback,
    data: dict[str, Any],
) -> dict[str, Any]:
    """内存版 interrupt：asyncio.Event 等待 resume。"""
    _active_interrupt_keys.add(key)
    event = asyncio.Event()
    _memory_events[key] = event
    try:
        interrupt_id = f"mem-{uuid.uuid4().hex[:8]}"
        await callback(data, interrupt_id)
        # 挂起协程，等待 resume_memory() 调用 event.set()
        # 加超时保护，防止用户关浏览器后永久挂起
        try:
            await asyncio.wait_for(event.wait(), timeout=_MEMORY_INTERRUPT_TIMEOUT)
        except asyncio.TimeoutError:
            raise TimeoutError("用户未在规定时间内响应，操作已取消")
        return _memory_responses.pop(key, {})
    finally:
        _active_interrupt_keys.discard(key)
        _memory_events.pop(key, None)
        _memory_responses.pop(key, None)


async def resume_memory(key: str, data: dict[str, Any]) -> None:
    """恢复内存模式的 interrupt。"""
    event = _memory_events.get(key)
    if event is None:
        raise RuntimeError(f"Interrupt '{key}' 不存在或已完成")
    _memory_responses[key] = data
    event.set()


# ═══════════════════════════════════════════════
#  Temporal 模式
# ═══════════════════════════════════════════════

def _import_temporal():
    """延迟导入 Temporal（未安装时不报错，只在实际使用时才需要）。"""
    from temporalio import workflow
    from temporalio.client import Client, WorkflowExecutionStatus
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker
    return workflow, Client, WorkflowExecutionStatus, UnsandboxedWorkflowRunner, Worker


# Temporal Workflow 定义（仅在 temporalio 可用时注册）
try:
    from temporalio import workflow as _wf
    from temporalio.client import Client as _Client, WorkflowExecutionStatus as _WfStatus
    from temporalio.worker import UnsandboxedWorkflowRunner as _UnsandboxedRunner, Worker as _Worker

    @_wf.defn
    class InterruptWorkflow:
        """纯等待 Workflow —— 不执行任何 Activity，只等 resume 信号。"""

        def __init__(self) -> None:
            self._response: dict[str, Any] | None = None
            self._callback_done: bool = False

        @_wf.signal
        async def on_resume(self, data: dict[str, Any]) -> None:
            self._response = data

        @_wf.signal
        async def on_callback_done(self) -> None:
            self._callback_done = True

        @_wf.query
        def status(self) -> str:
            if self._response is not None:
                return "resumed"
            if self._callback_done:
                return "waiting"
            return "pending"

        @_wf.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            await _wf.wait_condition(lambda: self._callback_done)
            await _wf.wait_condition(lambda: self._response is not None)
            return self._response  # type: ignore[return-value]

    _TEMPORAL_AVAILABLE = True
except ImportError:
    _TEMPORAL_AVAILABLE = False


async def _interrupt_temporal(
    client: Any,
    key: str,
    callback: InterruptCallback,
    data: dict[str, Any],
    *,
    task_queue: str,
    task_timeout: timedelta,
) -> dict[str, Any]:
    """Temporal 版 interrupt（原有逻辑，未改动）。"""
    if not _TEMPORAL_AVAILABLE:
        raise RuntimeError("temporalio 未安装，无法使用 Temporal 模式")

    _active_interrupt_keys.add(key)
    try:
        handle = None

        # 尝试获取已存在的 Workflow（重连场景）
        try:
            handle = client.get_workflow_handle(key)
            desc = await handle.describe()

            if desc.status == _WfStatus.RUNNING:
                status = await handle.query(InterruptWorkflow.status)
                interrupt_id = desc.run_id

                if status == "waiting":
                    return await handle.result()

                if status == "pending":
                    await callback(data, interrupt_id)
                    await handle.signal(InterruptWorkflow.on_callback_done)
                    return await handle.result()

            if desc.status == _WfStatus.COMPLETED:
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
    finally:
        _active_interrupt_keys.discard(key)


async def resume_temporal(client: Any, key: str, data: dict[str, Any]) -> None:
    """恢复 Temporal 模式的 interrupt。"""
    if not _TEMPORAL_AVAILABLE:
        raise RuntimeError("temporalio 未安装")

    handle = client.get_workflow_handle(key)

    status = await handle.query(InterruptWorkflow.status)
    if status == "pending":
        raise RuntimeError(f"Interrupt '{key}' 尚未就绪（callback 未完成），不能 resume")

    await handle.signal(InterruptWorkflow.on_resume, data)


def create_interrupt_worker(
    client: Any,
    *,
    task_queue: str = "interrupt-queue",
) -> Any:
    """创建 interrupt Worker（只处理 Workflow，无状态）。"""
    if not _TEMPORAL_AVAILABLE:
        raise RuntimeError("temporalio 未安装")

    from agent_sdk._config.settings import get_temporal_config

    debug_mode = get_temporal_config().debug_mode
    return _Worker(
        client,
        task_queue=task_queue,
        workflows=[InterruptWorkflow],
        debug_mode=debug_mode,
        workflow_runner=_UnsandboxedRunner(),
    )


# ═══════════════════════════════════════════════
#  统一入口
# ═══════════════════════════════════════════════

async def interrupt(
    client: Any | None,
    key: str,
    callback: InterruptCallback,
    data: dict[str, Any],
    *,
    task_queue: str = "interrupt-queue",
    task_timeout: timedelta = timedelta(seconds=10),
) -> dict[str, Any]:
    """发起 interrupt，阻塞直到用户 resume。

    client=None → 内存模式（TEMPORAL_ENABLED=false）
    client≠None → Temporal 模式（不降级，连接失败直接报错）
    """
    if client is None:
        return await _interrupt_memory(key, callback, data)

    return await _interrupt_temporal(
        client, key, callback, data,
        task_queue=task_queue, task_timeout=task_timeout,
    )


async def resume(client: Any | None, key: str, data: dict[str, Any]) -> None:
    """恢复一个等待中的 interrupt。

    client=None → 内存模式
    client≠None → Temporal 模式
    """
    if client is None:
        await resume_memory(key, data)
    else:
        await resume_temporal(client, key, data)

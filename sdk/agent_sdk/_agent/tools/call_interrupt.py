"""call_interrupt：在 tool 内部暂停执行，等待用户回复后继续。

这是一个工具函数（utility），不是 LLM tool。任何 tool 内部需要用户输入时调用它。

使用方式：
    from agent_sdk._agent.tools.call_interrupt import call_interrupt

    async def my_tool(ctx: RunContext[AgentDeps], ...) -> str:
        reply = await call_interrupt(ctx, {
            "type": "confirm",
            "question": "确认操作？",
        })
        if reply == "确认":
            ...

适用场景：
- mainagent tool（如 ask_car_info）需要用户录入信息
- subagent tool（如 find_best_price）需要用户确认
- 任何需要暂停 agent loop 等待用户的场景

机制：
    生成 interrupt_key → emit INTERRUPT 事件 → 等待用户 resume → 返回回复
    TEMPORAL_ENABLED=true 时通过 Temporal Workflow 等待（持久化）
    TEMPORAL_ENABLED=false 时通过 asyncio.Event 等待（内存，开发/测试用）
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.interrupt import interrupt as _do_interrupt
from agent_sdk._config.settings import get_temporal_config
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


async def call_interrupt(
    ctx: RunContext[AgentDeps],
    data: dict[str, Any],
) -> str:
    """暂停 agent 执行，向前端发送 interrupt 事件，等待用户回复。

    Args:
        ctx: Pydantic AI RunContext，提供 deps（emitter, temporal_client 等）
        data: 发给前端的数据，通常包含：
            - question (str): 显示给用户的问题
            - type (str): 卡片类型，如 "confirm", "input", "select"
            - 其他业务字段（前端自定义渲染用）

    Returns:
        用户的回复文本。dict 类型回复会被序列化为 JSON 字符串。

    Raises:
        RuntimeError: 内部错误时抛出。
    """
    emitter = ctx.deps.emitter
    session_id = ctx.deps.session_id
    temporal_client = ctx.deps.temporal_client

    # 生成唯一 interrupt key
    interrupt_key = f"interrupt-{session_id}-{uuid.uuid4().hex[:8]}"

    # callback：发 interrupt 事件给前端（带 interrupt_id）
    async def _emit_interrupt(callback_data: dict[str, Any], interrupt_id: str) -> None:
        if emitter is not None:
            await emitter.emit(EventModel(
                session_id=session_id,
                request_id=ctx.deps.request_id,
                type=EventType.INTERRUPT,
                data={
                    **data,
                    "interrupt_id": interrupt_id,
                    "interrupt_key": interrupt_key,
                },
            ))

    # 调用 interrupt 抽象层 — 在这里 await 直到用户 resume
    config = get_temporal_config()
    response = await _do_interrupt(
        temporal_client,
        key=interrupt_key,
        callback=_emit_interrupt,
        data=data,
        task_queue=config.interrupt_task_queue,
    )

    # 返回用户回复
    user_reply = response.get("reply", "")
    if isinstance(user_reply, dict):
        return json.dumps(user_reply, ensure_ascii=False)
    return str(user_reply)

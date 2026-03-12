"""ask_user 工具：暂停 agent 执行，等待用户提供信息后继续。

真正暂停 agent loop，await 直到用户回复，然后继续执行。
依赖 Temporal interrupt 抽象层，未配置 Temporal 时报错。
"""

from __future__ import annotations

import json
import uuid

from pydantic_ai import RunContext

from src.sdk._agent.deps import AgentDeps
from src.sdk._agent.interrupt import interrupt as _do_interrupt
from src.sdk._config.settings import get_temporal_config
from src.sdk._event.event_model import EventModel
from src.sdk._event.event_type import EventType


async def ask_user(
    ctx: RunContext[AgentDeps],
    question: str,
    type: str = "confirm",
    data: str = "{}",
) -> str:
    """Pause execution and ask the user for information. Resumes when the user replies.

    Use this when you need user confirmation, additional details, or a choice
    before proceeding. The agent loop will pause until the user responds.

    Args:
        question: The question to display to the user.
        type: Card type for frontend rendering (e.g. "confirm", "input", "select").
        data: Optional JSON string with extra data for the card.

    Returns:
        The user's reply as a string (JSON if structured, plain text otherwise).
    """
    emitter = ctx.deps.emitter
    session_id = ctx.deps.session_id
    temporal_client = ctx.deps.temporal_client

    # 解析 data JSON
    try:
        parsed_data = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        parsed_data = {"raw": data}

    # 生成唯一 interrupt key
    interrupt_key = f"interrupt-{session_id}-{uuid.uuid4().hex[:8]}"

    # callback：发 interrupt 事件给前端（带 interrupt_id）
    async def _emit_interrupt(callback_data: dict, interrupt_id: str) -> None:
        if emitter is not None:
            await emitter.emit(EventModel(
                session_id=session_id,
                request_id="",
                type=EventType.INTERRUPT,
                data={
                    "type": type,
                    "question": question,
                    "interrupt_id": interrupt_id,
                    "interrupt_key": interrupt_key,
                    **parsed_data,
                },
            ))

    # 调用 interrupt 抽象层 — 在这里 await 直到用户 resume
    config = get_temporal_config()
    response = await _do_interrupt(
        temporal_client,
        key=interrupt_key,
        callback=_emit_interrupt,
        data={"question": question, "type": type, **parsed_data},
        task_queue=config.interrupt_task_queue,
    )

    # 返回用户回复给 LLM
    user_reply = response.get("reply", "")
    if isinstance(user_reply, dict):
        return json.dumps(user_reply, ensure_ascii=False)
    return str(user_reply)

"""ask_user 工具：暂停 agent 执行，等待用户提供信息后继续。

与旧 interrupt 工具的区别：
- 旧 interrupt：fire-and-forget，发完卡片立即返回，用户反馈靠下一条消息
- ask_user：真正暂停 agent loop，await 直到用户回复，然后继续执行

内部使用 Temporal interrupt 抽象层，tool 代码不包含任何 Temporal 细节。
"""

from __future__ import annotations

import json
import logging
import uuid

from pydantic_ai import RunContext

from src.agent.deps import AgentDeps
from src.agent.interrupt import interrupt as _do_interrupt
from src.config.settings import get_temporal_config
from src.event.event_model import EventModel
from src.event.event_type import EventType

logger = logging.getLogger(__name__)


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

    # 无 Temporal client 时 fallback 到 fire-and-forget 模式
    if temporal_client is None:
        logger.warning("ask_user: no temporal_client, falling back to fire-and-forget")
        if emitter is not None:
            await emitter.emit(EventModel(
                session_id=session_id,
                request_id="",
                type=EventType.INTERRUPT,
                data={"type": type, "question": question, **parsed_data},
            ))
        return "已向用户展示问题，等待用户在下一轮消息中反馈。不要猜测用户的选择，等待用户回复。"

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

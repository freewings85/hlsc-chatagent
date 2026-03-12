"""PriceFinder Subagent 工具集。"""

from __future__ import annotations

import json

from pydantic_ai import RunContext

from src.sdk._agent.deps import AgentDeps
from src.sdk._agent.interrupt import interrupt as _do_interrupt
from src.sdk._config.settings import get_temporal_config
from src.sdk._event.event_model import EventModel
from src.sdk._event.event_type import EventType


async def find_best_price_of_project(
    ctx: RunContext[AgentDeps],
    project_name: str,
) -> str:
    """Find the best (cheapest) price for a car repair project across all shops.

    This tool searches for the best price and asks the user to confirm before
    returning the final result.

    Args:
        project_name: The name of the car repair project to search for.

    Returns:
        The best price result as a string.
    """
    emitter = ctx.deps.emitter
    session_id = ctx.deps.session_id
    temporal_client = ctx.deps.temporal_client

    # 模拟：查找到最低价
    mock_price = 500
    mock_shop = "张江汽修中心"

    # 通过 interrupt 让用户确认
    import uuid

    interrupt_key = f"interrupt-{session_id}-{uuid.uuid4().hex[:8]}"

    question = (
        f"找到项目「{project_name}」的最低报价：\n"
        f"门店：{mock_shop}\n"
        f"价格：{mock_price} 元\n\n"
        f"确认选择此方案吗？"
    )

    async def _emit_interrupt(callback_data: dict, interrupt_id: str) -> None:
        if emitter is not None:
            await emitter.emit(EventModel(
                session_id=session_id,
                request_id="",
                type=EventType.INTERRUPT,
                data={
                    "type": "confirm",
                    "question": question,
                    "interrupt_id": interrupt_id,
                    "interrupt_key": interrupt_key,
                },
            ))

    config = get_temporal_config()
    response = await _do_interrupt(
        temporal_client,
        key=interrupt_key,
        callback=_emit_interrupt,
        data={"question": question, "type": "confirm"},
        task_queue=config.interrupt_task_queue,
    )

    user_reply = response.get("reply", "")
    if user_reply in ("确认", "yes", "确定", "ok"):
        return (
            f"用户已确认。项目「{project_name}」最优方案：\n"
            f"门店：{mock_shop}\n"
            f"价格：{mock_price} 元"
        )
    else:
        return f"用户取消了项目「{project_name}」的询价。"


# 工具列表
PRICE_FINDER_TOOLS: list[str] = ["find_best_price_of_project"]


def create_price_finder_tool_map() -> dict:
    """创建 price_finder 工具映射。"""
    return {
        "find_best_price_of_project": find_best_price_of_project,
    }

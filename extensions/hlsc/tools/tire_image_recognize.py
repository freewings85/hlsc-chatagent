"""tire_image_recognize 工具：轮胎照片识别规格（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def tire_image_recognize(
    ctx: RunContext[AgentDeps],
    image_url: Annotated[str, Field(description="轮胎照片 URL")],
) -> str:
    """识别轮胎照片中的规格信息（如 225/45R17）。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("tire_image_recognize", sid, rid, {"image_url": image_url})
    log_tool_end("tire_image_recognize", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "tire_image_recognize 尚未实现，请引导车主手动输入轮胎规格"}'

"""ask_user_location 工具：让用户提供位置信息。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("ask_user_location")


async def ask_user_location(
    ctx: RunContext[AgentDeps],
    reason: Annotated[str, Field(description="需要位置信息的原因，如'查询附近门店需要知道您的位置'")],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("ask_user_location", sid, rid, {"reason": reason})

    try:
        reply = await call_interrupt(ctx, {
            "type": "select_location",
            "question": reason,
        })

        try:
            data = json.loads(reply)
            address = data.get("address", "")
            lat = data.get("lat")
            lng = data.get("lng")
            if lat and lng:
                log_tool_end("ask_user_location", sid, rid, {"address": address, "lat": lat, "lng": lng})
                return f"用户选择位置：address={address}, lat={lat}, lng={lng}"
        except (json.JSONDecodeError, AttributeError):
            pass

        if reply:
            log_tool_end("ask_user_location", sid, rid, {"raw_reply": reply})
            return f"用户回复：{reply}"

        log_tool_end("ask_user_location", sid, rid, {"result": "no_location"})
        return "用户未提供位置信息"

    except Exception as e:
        log_tool_end("ask_user_location", sid, rid, exc=e)
        return f"Error: ask_user_location failed - {e}"


ask_user_location.__doc__ = _DESCRIPTION

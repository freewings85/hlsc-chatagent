"""fuzzy_match_location 工具：根据地名模糊匹配位置，获取经纬度。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("fuzzy_match_location")


async def fuzzy_match_location(
    ctx: RunContext[AgentDeps],
    keyword: Annotated[str, Field(description="地名关键词，如'静安'、'浦东张江'、'徐汇漕河泾'")],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("fuzzy_match_location", sid, rid, {"keyword": keyword})

    try:
        reply = await call_interrupt(ctx, {
            "type": "select_location",
            "question": f"请确认位置：{keyword}",
            "keyword": keyword,
        })

        try:
            data = json.loads(reply)
            address = data.get("address", "")
            lat = data.get("lat")
            lng = data.get("lng")
            if lat and lng:
                log_tool_end("fuzzy_match_location", sid, rid, {"address": address, "lat": lat, "lng": lng})
                return f"用户确认位置：address={address}, lat={lat}, lng={lng}"
        except (json.JSONDecodeError, AttributeError):
            pass

        if reply:
            log_tool_end("fuzzy_match_location", sid, rid, {"raw_reply": reply})
            return f"用户回复：{reply}"

        log_tool_end("fuzzy_match_location", sid, rid, {"result": "no_location"})
        return "用户未提供位置信息"

    except Exception as e:
        log_tool_end("fuzzy_match_location", sid, rid, exc=e)
        return f"Error: fuzzy_match_location failed - {e}"


fuzzy_match_location.__doc__ = _DESCRIPTION

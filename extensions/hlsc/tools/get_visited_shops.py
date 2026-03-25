"""get_visited_shops 工具：查询用户去过的商户（上次去过或历史去过）。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.shop_service import shop_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("get_visited_shops")


async def get_visited_shops(
    ctx: RunContext[AgentDeps],
    query_type: Annotated[
        str, Field(description="查询类型：'latest'=上次去过的，'history'=历史去过的")
    ],
    top: Annotated[int, Field(description="返回数量")] = 5,
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    owner_id = ctx.deps.user_id
    log_tool_start("get_visited_shops", sid, rid, {
        "query_type": query_type, "top": top, "owner_id": owner_id,
    })

    if owner_id == "anonymous":
        log_tool_end("get_visited_shops", sid, rid, {"error": "user not identified"})
        return "无法查询：当前用户未登录"

    try:
        if query_type == "latest":
            result = await shop_service.get_latest_visited_shops(
                owner_id=owner_id, top=top,
                session_id=sid, request_id=rid,
            )
        else:
            result = await shop_service.get_history_visited_shops(
                owner_id=owner_id, top=top,
                session_id=sid, request_id=rid,
            )

        raw_list = result if isinstance(result, list) else result.get("commercials", [])
        if not raw_list:
            log_tool_end("get_visited_shops", sid, rid, {"shop_count": 0})
            type_label = "上次去过的" if query_type == "latest" else "历史去过的"
            return f"未找到{type_label}商户记录"

        shops = []
        for item in raw_list:
            shops.append({
                "shop_id": item.get("commercialId", ""),
                "name": item.get("commercialName", ""),
            })

        log_tool_end("get_visited_shops", sid, rid, {
            "shop_count": len(shops),
            "shops": [s["name"] for s in shops],
        })
        return json.dumps({"total": len(shops), "shops": shops}, ensure_ascii=False)

    except Exception as e:
        log_tool_end("get_visited_shops", sid, rid, exc=e)
        return f"Error: get_visited_shops failed - {e}"


get_visited_shops.__doc__ = _DESCRIPTION

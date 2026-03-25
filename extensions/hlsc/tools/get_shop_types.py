"""get_shop_types 工具：获取所有商户类型列表。"""

from __future__ import annotations

import json

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.shop_service import shop_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("get_shop_types")


async def get_shop_types(
    ctx: RunContext[AgentDeps],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("get_shop_types", sid, rid, {})

    try:
        result = await shop_service.get_all_shop_types(
            session_id=sid, request_id=rid,
        )

        type_list = result if isinstance(result, list) else []
        if not type_list:
            log_tool_end("get_shop_types", sid, rid, {"type_count": 0})
            return "未找到商户类型数据"

        log_tool_end("get_shop_types", sid, rid, {"type_count": len(type_list)})
        return json.dumps({"total": len(type_list), "types": type_list}, ensure_ascii=False)

    except Exception as e:
        log_tool_end("get_shop_types", sid, rid, exc=e)
        return f"Error: get_shop_types failed - {e}"


get_shop_types.__doc__ = _DESCRIPTION

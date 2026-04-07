"""update_session_state 工具：更新会话级状态（project_id, shop_id 等已确认信息）。

工具调用后，session_state 内容会注入到下一轮 LLM 调用的 context_message 中，
确保 LLM 每轮都能看到最新的已确认信息。
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.messages import UserPromptPart

from agent_sdk._agent.deps import AgentDeps, format_session_state
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("update_session_state")


async def update_session_state(
    ctx: RunContext[AgentDeps],
    updates: Annotated[dict[str, Any], Field(
        description="要更新的实体列表。字段：carModels([{id,name}]), addresses([{name}]), projects([{id,name}]), shops([{id,name}]), coupons([{id,name}])。value 为 null 表示清除"
    )],
) -> str:
    """更新会话状态。当通过工具调用获得关键信息（项目、商户、车型等）后，用此工具记录已确认的信息，后续轮次可直接使用，避免重复查询。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_session_state", sid, rid, {"updates": updates})

    try:
        # 1. 更新 deps.session_state
        for key, value in updates.items():
            if value is None:
                # None 值表示清除该字段
                ctx.deps.session_state.pop(key, None)
            else:
                ctx.deps.session_state[key] = value

        # 2. 刷新 context_message 内容（如果占位引用存在）
        if ctx.deps._session_state_msg is not None:
            new_content: str = format_session_state(ctx.deps.session_state)
            ctx.deps._session_state_msg.parts = [UserPromptPart(content=new_content)]

        # 2.5 持久化到文件（跨轮次保留）
        session_state_service = getattr(ctx.deps, "_session_state_service", None)
        if session_state_service is not None:
            user_id: str = ctx.deps.user_id if hasattr(ctx.deps, "user_id") else ""
            session_state_service.save(user_id, sid, ctx.deps.session_state)

        # 3. 构建确认信息
        updated_keys: list[str] = list(updates.keys())
        current_state: str = json.dumps(ctx.deps.session_state, ensure_ascii=False)
        result: str = f"已更新 session_state: {updated_keys}。当前完整状态: {current_state}"

        log_tool_end("update_session_state", sid, rid, {"updated_keys": updated_keys})
        return result

    except Exception as e:
        log_tool_end("update_session_state", sid, rid, exc=e)
        return f"Error: update_session_state failed - {e}"


update_session_state.__doc__ = _DESCRIPTION

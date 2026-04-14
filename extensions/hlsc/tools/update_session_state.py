"""update_session_state 工具：写入会话级状态（降级 / 非编排场景用）。

写入本地 ctx.deps.session_state dict，持久化到文件（SessionStateService），
刷新 context_message 占位。适用于 ChatManager 直连 ChatAgent、没有 workflow 编排的场景。

编排场景请用 update_workflow_state（走 Temporal update 推进 workflow）。
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
        description="要更新/收集的字段。key 是字段名，value 是字段值。None 值表示删除该字段。"
    )],
) -> str:
    """收集关键业务字段到会话状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_session_state", sid, rid, {"updates": updates})

    try:
        for key, value in updates.items():
            if value is None:
                ctx.deps.session_state.pop(key, None)
            else:
                ctx.deps.session_state[key] = value

        if ctx.deps._session_state_msg is not None:
            new_content: str = format_session_state(ctx.deps.session_state)
            ctx.deps._session_state_msg.parts = [UserPromptPart(content=new_content)]

        session_state_service = getattr(ctx.deps, "_session_state_service", None)
        if session_state_service is not None:
            user_id: str = ctx.deps.user_id if hasattr(ctx.deps, "user_id") else ""
            session_state_service.save(user_id, sid, ctx.deps.session_state)

        updated_keys: list[str] = list(updates.keys())
        current_state: str = json.dumps(ctx.deps.session_state, ensure_ascii=False)
        log_tool_end("update_session_state", sid, rid, {"updated_keys": updated_keys})
        return f"已更新 session_state: {updated_keys}。当前完整状态: {current_state}"
    except Exception as e:
        log_tool_end("update_session_state", sid, rid, exc=e)
        return f"Error: update_session_state failed - {e}"


update_session_state.__doc__ = _DESCRIPTION

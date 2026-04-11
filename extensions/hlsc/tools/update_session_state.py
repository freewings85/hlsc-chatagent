"""update_session_state 工具：更新会话级状态。

两种运行模式：

1. **降级模式**（ctx.deps.workflow_id 为 None）：
   走原有行为——写入本地 ctx.deps.session_state dict，持久化到文件（SessionStateService），
   刷新 context_message 占位。这是 ChatManager 直连 ChatAgent 场景下的经典路径。

2. **Orchestrator 编排模式**（ctx.deps.workflow_id 非空）：
   - 本地预校验：检查 fields 是否齐、advance_to 是否在 current_step.allowed_next 里
   - 同 turn 单次推进守卫：ctx.deps._step_mutation_committed 第一次成功后置 True
   - 调 orchestrator 的 /internal/advance_step 代理（带 fields_values，让 orchestrator
     代写 MySQL session_states，mainagent 不引入 MySQL 依赖）
   - 同步拿结果，失败时返回具体的 MISSING_FIELDS / ILLEGAL_TRANSITION / ... 错误码

详见 design.md §8.3。
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import httpx
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
        description="要更新/收集的字段。orchestrator 模式下这些字段必须对应 current_step.expected_fields；降级模式下保留原语义"
    )],
    advance_to: Annotated[str | None, Field(
        description="orchestrator 模式专用：收集到全部 expected_fields 后声明推进到的下一 step id（END 表示流程结束）。降级模式下传 None"
    )] = None,
    revert_to: Annotated[str | None, Field(
        description="orchestrator 模式专用：回退到某个已完成 step。降级模式下传 None"
    )] = None,
    revert_reason: Annotated[str | None, Field(
        description="回退原因（用户角度的描述）"
    )] = None,
) -> str:
    """收集关键业务字段并推进业务流程状态。orchestrator 模式下同步返回校验结果。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_session_state", sid, rid, {
        "updates": updates, "advance_to": advance_to, "revert_to": revert_to,
    })

    # ══════════════════════════════════════════════════════════
    # 降级模式：没接 orchestrator，走原语义
    # ══════════════════════════════════════════════════════════
    if ctx.deps.workflow_id is None:
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

    # ══════════════════════════════════════════════════════════
    # Orchestrator 编排模式
    # ══════════════════════════════════════════════════════════

    # 1. 同 turn 单次推进守卫（放最前面，防止污染 session_state）
    if (advance_to or revert_to) and ctx.deps._step_mutation_committed:
        log_tool_end("update_session_state", sid, rid, {"blocked": "already_committed"})
        return (
            "error: 本 turn 已成功完成一次 step 推进/回退，不能再推进第二次。"
            "多余的推进请求不应该出现，请直接生成 final 回复结束本轮。"
        )

    # 2. 本地预校验（快速失败，不发网络请求）
    current_step_detail: dict[str, Any] | None = ctx.deps.current_step_detail
    if advance_to is not None:
        if current_step_detail is None:
            return "error: orchestrator 模式下缺少 current_step_detail，无法做本地预校验"

        required_fields: set[str] = {
            f["name"] for f in current_step_detail.get("expected_fields", [])
        }
        # 合并：本次 updates 写入 + 之前 session_state 已有
        already_have: set[str] = set(ctx.deps.session_state.keys())
        will_have: set[str] = already_have | set(updates.keys())
        missing: list[str] = sorted(required_fields - will_have)
        if missing:
            log_tool_end("update_session_state", sid, rid, {"missing": missing})
            return f"missing_fields: {', '.join(missing)}. 请先收集这些字段，不要声称已完成。"

        allowed_next: list[str] = current_step_detail.get("allowed_next", [])
        if advance_to != "END" and advance_to not in allowed_next:
            return (
                f"illegal_transition: {advance_to} 不在 allowed_next={allowed_next}。"
                f"本 step 的合法后继只有这些。"
            )

    # 3. 调 orchestrator 代理
    orch_url: str = ctx.deps.orchestrator_url or ""
    if not orch_url:
        return "error: orchestrator_url 为空，无法调用 /internal/advance_step"

    op: str = "advance" if advance_to is not None else "revert"
    target: str = advance_to or revert_to or ""
    update_id: str = f"{op}-{rid}-{target}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if advance_to is not None:
                assert current_step_detail is not None
                resp: httpx.Response = await client.post(
                    f"{orch_url}/internal/advance_step",
                    json={
                        "workflow_id": ctx.deps.workflow_id,
                        "update_id": update_id,
                        "user_id": ctx.deps.user_id,
                        "session_id": sid,
                        "current_step": current_step_detail["id"],
                        "target_step": advance_to,
                        "fields_written": list(updates.keys()),
                        "fields_values": updates,
                    },
                )
            else:
                resp = await client.post(
                    f"{orch_url}/internal/revert_step",
                    json={
                        "workflow_id": ctx.deps.workflow_id,
                        "user_id": ctx.deps.user_id,
                        "session_id": sid,
                        "update_id": update_id,
                        "revert_to": revert_to,
                        "reason": revert_reason or "",
                    },
                )
    except httpx.TimeoutException:
        log_tool_end("update_session_state", sid, rid, exc=TimeoutError("orchestrator timeout"))
        return (
            "error: orchestrator timeout. 推进请求未被确认，"
            "请在回复中告诉用户系统繁忙稍后再试。"
        )
    except Exception as e:
        log_tool_end("update_session_state", sid, rid, exc=e)
        return f"error: orchestrator call failed - {e}"

    if resp.status_code == 200:
        # 标记本 turn 已推进（同 turn 单次守卫的"开关"）
        ctx.deps._step_mutation_committed = True
        # 同时刷新本地 session_state（方便 LLM 在后续工具调用里看到最新字段）
        for k, v in updates.items():
            if v is None:
                ctx.deps.session_state.pop(k, None)
            else:
                ctx.deps.session_state[k] = v
        if ctx.deps._session_state_msg is not None:
            new_content = format_session_state(ctx.deps.session_state)
            ctx.deps._session_state_msg.parts = [UserPromptPart(content=new_content)]
        log_tool_end("update_session_state", sid, rid, {
            "op": op, "target": target, "fields": list(updates.keys()),
        })
        return "ok"

    # 4xx：validator 拒了
    detail: dict = resp.json()
    err_code: str = detail.get("error_code", "unknown")
    err_msg: str = detail.get("message", "")
    log_tool_end("update_session_state", sid, rid, {"rejected": err_code})
    return f"{err_code}: {err_msg}"


update_session_state.__doc__ = _DESCRIPTION

"""update_workflow_state 工具：把收集到的业务字段同步写入 Workflow 状态。

**仅 orchestrator 编排模式下可用**（ctx.deps.workflow_id 非空时）。
降级模式下此工具不注册。

调用链路：
    Agent LLM 调用此工具
    → tool 从 deps 取 temporal_client + workflow_id
    → handle.execute_update("on_state_changed", StateChangeRequest(fields={...}))
    → Workflow 内部：写 MySQL + 判断推进 + 推进时执行业务 activity
    → 返回 StateChangeResult（current_step / advanced / business_result / ...）
    → tool 如果推进了：热切换 prompt + 工具 + 刷新 session_state
    → tool 把结果（含业务数据）返回给 LLM

**跃迁时单次 agent 调用**：推进后不 suppress，不需要 workflow 再调一次 agent。
工具直接热切换 deps（available_tools / system_prompt_override / session_state），
LLM 在同一轮对话中基于新 prompt + 业务数据生成展示回复。
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("update_workflow_state")


async def update_workflow_state(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"xxxxxx\", \"register_date\": \"xxxxx\"}"
    )],
) -> str:
    """把收集到的信息写入流程状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_workflow_state", sid, rid, {"fields": list(fields.keys())})

    # 取 Temporal client 和 workflow_id
    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end("update_workflow_state", sid, rid, exc=RuntimeError("not in orchestrator mode"))
        return "error: 当前不在编排模式下，无法更新 workflow 状态"

    try:
        from orchestrator_protocol import StateChangeRequest, StateChangeResult

        handle = temporal_client.get_workflow_handle(workflow_id)
        result: StateChangeResult = await handle.execute_update(
            "on_state_changed",
            StateChangeRequest(
                user_id=ctx.deps.user_id,
                session_id=ctx.deps.session_id,
                fields=fields,
            ),
            result_type=StateChangeResult,
            rpc_timeout=timedelta(seconds=60),
        )

        # 同步刷新本地 session_state（后续工具调用能看到最新值）
        for k, v in fields.items():
            if v is None:
                ctx.deps.session_state.pop(k, None)
            else:
                ctx.deps.session_state[k] = v

        if not result.advanced:
            summary: str = f"ok. 当前仍在 {result.current_step}"
            if result.message:
                summary += f" ({result.message})"
            log_tool_end("update_workflow_state", sid, rid, {
                "current_step": result.current_step, "advanced": False,
            })
            return summary

        # ── 跃迁：热切换 prompt + 工具 + session_state ──

        # 1. 刷新 session_state（含业务 activity 写入的结果）
        if result.new_session_state:
            ctx.deps.session_state.update(result.new_session_state)

        # 2. 切换可用工具（DynamicToolset per_run_step=True 下一步自动生效）
        if result.new_available_tools:
            # 保留 Skill 工具（如果有）
            has_skill: bool = "Skill" in ctx.deps.available_tools
            ctx.deps.available_tools = list(result.new_available_tools)
            if has_skill and "Skill" not in ctx.deps.available_tools:
                ctx.deps.available_tools.append("Skill")

        # 3. 更新 deps 上的编排字段
        ctx.deps.current_step_detail = result.new_step_detail or None
        ctx.deps.step_skeleton = result.new_step_skeleton or None
        ctx.deps.step_pending_fields = (
            _calc_pending(result.new_step_detail, ctx.deps.session_state)
            if result.new_step_detail else []
        )

        # 4. 热切换 system prompt（下次 ModelRequestNode 前生效）
        _update_orchestrator_prompt(ctx.deps, result)

        # 5. 构造返回给 LLM 的文本（含业务数据，让 LLM 直接展示）
        summary = _build_advance_summary(result)

        log_tool_end("update_workflow_state", sid, rid, {
            "current_step": result.current_step,
            "advanced": True,
            "business_keys": list(result.business_result.keys()) if result.business_result else [],
        })
        return summary

    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        return f"error: update_workflow_state failed - {e}"


def _calc_pending(step_detail: dict[str, Any], session_state: dict[str, Any]) -> list[str]:
    """计算新 step 的待收集字段。"""
    expected: list[dict[str, str]] = step_detail.get("expected_fields", [])
    required: set[str] = {f["name"] for f in expected}
    return sorted(required - set(session_state.keys()))


def _update_orchestrator_prompt(deps: AgentDeps, result: Any) -> None:
    """用新 step 信息重建 orchestrator prompt 并设置 system_prompt_override。"""
    try:
        from agent_sdk._agent.orchestrator_prompt import render_orchestrator_prompt

        new_prompt: str = render_orchestrator_prompt(
            step_skeleton=result.new_step_skeleton,
            current_step=result.new_step_detail,
            session_state=deps.session_state,
            step_pending_fields=deps.step_pending_fields or [],
        )
        deps.system_prompt_override = new_prompt
    except Exception:
        pass  # prompt 切换失败不影响功能，tool result 仍然引导 LLM


def _build_advance_summary(result: Any) -> str:
    """构造跃迁后返回给 LLM 的自然语言文本。"""
    parts: list[str] = [f"ok. 已写入。"]

    # 业务结果
    if result.business_result:
        parts.append(f"业务数据：{json.dumps(result.business_result, ensure_ascii=False)}")

    # 新 step 目标
    new_detail: dict[str, Any] = result.new_step_detail or {}
    if new_detail.get("goal"):
        parts.append(f"接下来：{new_detail['goal']}")

    return "\n".join(parts)


update_workflow_state.__doc__ = _DESCRIPTION

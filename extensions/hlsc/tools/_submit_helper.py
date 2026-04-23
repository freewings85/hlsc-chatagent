"""场景级「提交事实到 workflow」工具的共享底座。

所有 submit_*/report_* 类工具（按 scene 命名）都共用这套流程：
  LLM → scene 工具 → _submit_workflow_fields(fields, tool_name)
    → Temporal execute_update("on_state_changed", StateChangeRequest)
    → Workflow validate loop → StateChangeResult
    → 发 TOOL_RESULT_DETAIL 事件（前端渲染用）
    → 热切换 next_instruction
    → 返回 tool_result_message（LLM 可见）

任何失败统一 raise WorkflowUnavailableError，agent loop 会捕获终止本轮——
不给 LLM 看错误字符串，避免重试同一工具。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.exceptions import WorkflowUnavailableError
from agent_sdk.logging import log_tool_start, log_tool_end

_CALL_WORKFLOW_TIMEOUT: float = float(os.getenv("CALL_WORKFLOW_TIMEOUT", "120"))

_logger: logging.Logger = logging.getLogger(__name__)


async def submit_workflow_fields(
    ctx: RunContext[AgentDeps],
    fields: dict[str, Any],
    tool_name: str,
    detail_type: str = "workflow_result",
) -> str:
    """把 fields 提交给 workflow 的 on_state_changed，返回 tool_result_message。

    Args:
        ctx: Pydantic AI RunContext
        fields: 要登记到 workflow 状态的字段字典
        tool_name: 调用方工具名（日志 / TOOL_RESULT_DETAIL 事件用）
        detail_type: TOOL_RESULT_DETAIL 事件的 detail_type 字段，前端按这个值挑
            卡片组件。和 uniapp / web 约定的常量：
              · search_repair_shops  修理厂 / 4S 店卡片
              · diagnose             故障诊断
              · parts_price          零部件价格
              · projects_price       门店项目报价
              · place_bidding_order  竞价下单结果
              · workflow_result      通用兜底（无专用卡片时）

    Raises:
        WorkflowUnavailableError: temporal_client 缺失、超时、任何异常
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start(tool_name, sid, rid, {"fields": list(fields.keys())})

    if not fields:
        log_tool_end(tool_name, sid, rid, {"skipped": "empty_fields"})
        return "本次未提交任何字段，已忽略。"

    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end(tool_name, sid, rid, exc=RuntimeError("not in orchestrator mode"))
        raise WorkflowUnavailableError(
            "后端工作流连接不可用（temporal_client 或 workflow_id 缺失）"
        )

    try:
        from orchestrator_protocol import StateChangeRequest, StateChangeResult

        handle = temporal_client.get_workflow_handle(workflow_id)
        try:
            async with asyncio.timeout(_CALL_WORKFLOW_TIMEOUT):
                result: StateChangeResult = await handle.execute_update(
                    "on_state_changed",
                    StateChangeRequest(
                        user_id=ctx.deps.user_id,
                        session_id=ctx.deps.session_id,
                        fields=fields,
                    ),
                    result_type=StateChangeResult,
                )
        except asyncio.TimeoutError:
            log_tool_end(tool_name, sid, rid, exc=TimeoutError(f">{_CALL_WORKFLOW_TIMEOUT}s"))
            raise WorkflowUnavailableError(
                f"工作流响应超时（>{_CALL_WORKFLOW_TIMEOUT}s）"
            )

        # workflow 标 is_error → 计入 tool_error_count，累计超阈值 SDK loop 会硬停
        if getattr(result, "is_error", False):
            ctx.deps.tool_error_count += 1
            log_tool_end(
                tool_name, sid, rid,
                {"backend_error": True, "error_count": ctx.deps.tool_error_count},
            )

        # interrupt 分支：activity 显式要求阻塞问用户（如询价单已创建等用户确认）
        # 这里不设 next_instruction / 不 emit TOOL_RESULT_DETAIL，全部信息走 INTERRUPT 事件。
        # call_interrupt 会挂起本 tool，前端 resume 回来后把 reply 作为 tool_result 返回 LLM。
        interrupt_data = getattr(result, "interrupt", None)
        if interrupt_data is not None:
            from agent_sdk._agent.tools.call_interrupt import call_interrupt
            log_tool_end(tool_name, sid, rid, {"routed_to": "call_interrupt"})
            return await call_interrupt(ctx, interrupt_data)

        # workflow 返回的 next_instruction 是权威：
        #   非空 → 下一步要 LLM 继续采集／澄清（AICall）
        #   空串 → workflow 走到 END，不再需要采集，必须清掉旧指令，
        #          否则 LLM 下轮还会看到上一步的 "立即提交 xxx" 又调工具触发 dedup 死循环
        ctx.deps.instruction = result.next_instruction

        if result.tool_result_raw is not None and ctx.deps.emitter is not None:
            from agent_sdk._event.event_model import EventModel
            from agent_sdk._event.event_type import EventType
            _detail_tcid: str = ctx.tool_call_id or ""
            if _detail_tcid == "":
                # 和 loop.py 的 _check_tool_call_id 告警对齐，便于排查漏 id 的 case
                _logger.warning(
                    "tool_call_id 缺失 source=tool_result_detail tool_name=%s raw=%r",
                    ctx.tool_name or tool_name, ctx.tool_call_id,
                )
            await ctx.deps.emitter.emit(EventModel(
                session_id=sid,
                request_id=rid,
                type=EventType.TOOL_RESULT_DETAIL,
                data={
                    "tool_name": ctx.tool_name or tool_name,
                    "tool_call_id": _detail_tcid,
                    "detail_type": detail_type,
                    "data": result.tool_result_raw,
                },
            ))

        log_tool_end(tool_name, sid, rid, {
            "has_next_instruction": bool(result.next_instruction),
            "has_tool_result_raw": result.tool_result_raw is not None,
        })
        # activity 显式传空串时兜底，避免 LLM 拿到 "" 不知所措
        return result.tool_result_message or "已记录。"

    except WorkflowUnavailableError:
        raise
    except Exception as e:
        log_tool_end(tool_name, sid, rid, exc=e)
        raise WorkflowUnavailableError(
            f"工作流调用出错（{type(e).__name__}: {e}）"
        ) from e

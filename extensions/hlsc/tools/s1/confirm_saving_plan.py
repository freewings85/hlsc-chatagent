"""confirm_saving_plan 工具：确认省钱方案，触发 S1 → S2 升级。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

SavingMethod = Literal["platform_offer", "insurance_bidding", "merchant_promo"]

_DESCRIPTION: str = load_tool_prompt("confirm_saving_plan")


async def confirm_saving_plan(
    ctx: RunContext[AgentDeps],
    project_id: Annotated[str, Field(description="项目标识（来自 classify_project 返回的 project_id，保险类固定为 '9999'）")],
    project_name: Annotated[str, Field(description="项目名称（来自 classify_project 返回的 project_name，保险类固定为 '保险项目'）")],
    saving_method: Annotated[SavingMethod, Field(description="用户确认的省钱方式：platform_offer（平台优惠方式）/ insurance_bidding（保险竞价）/ merchant_promo（商户自有优惠）")],
) -> str:
    """确认省钱方案，记录项目和省钱方式。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, str] = {
        "project_id": project_id,
        "project_name": project_name,
        "saving_method": saving_method,
    }
    log_tool_start("confirm_saving_plan", sid, rid, params)

    # 通过 UserStatService 升级到 S2
    from hlsc.services.user_stat_service import user_stat_service

    await user_stat_service.upgrade_to_s2(ctx.deps.user_id)

    method_names: dict[str, str] = {
        "platform_offer": "平台优惠方式",
        "insurance_bidding": "保险竞价",
        "merchant_promo": "商户自有优惠",
    }
    method_label: str = method_names.get(saving_method, saving_method)

    result: str = f"已确认：项目「{project_name}」，省钱方式「{method_label}」。"
    log_tool_end("confirm_saving_plan", sid, rid, {"result": result})
    return result


confirm_saving_plan.__doc__ = _DESCRIPTION

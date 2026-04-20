"""submit_coupon_search_criteria：搜优惠活动场景专用的"登记找优惠活动条件"工具。

扁平版 schema：不再分 activity / shop 两维度；LLM 只抽一棵 query 树，LEAF.params
合并所有字段。后端 resolver 按字段名自动拆成 activity_query + shop_query。

typed 参数 = CouponSearchInfo Pydantic 模型。schema 通过 JSON Schema 暴露给 LLM
（tool-calling 阶段），instruction 层不再描述字段名和枚举值，避免对用户泄漏内部术语。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.models.coupon_search import CouponSearchInfo
from hlsc.tools._submit_helper import submit_workflow_fields
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("submit_coupon_search_criteria")


async def submit_coupon_search_criteria(
    ctx: RunContext[AgentDeps],
    coupon_search_info: Annotated[CouponSearchInfo, Field(
        description=(
            "找优惠活动条件整包。按当前对话里用户原话里明确说过的条件填；"
            "没说过的字段一律省略（不要传空串、不要照 description 回填）。"
        )
    )],
) -> str:
    """登记找优惠活动条件。"""
    payload: dict = coupon_search_info.model_dump(by_alias=True, exclude_none=True)
    if not payload.get("query"):
        return "本次未提交任何字段，已忽略。"

    return await submit_workflow_fields(
        ctx,
        {"coupon_search_info": payload},
        tool_name="submit_coupon_search_criteria",
        detail_type="search_coupons",
    )


submit_coupon_search_criteria.__doc__ = _DESCRIPTION

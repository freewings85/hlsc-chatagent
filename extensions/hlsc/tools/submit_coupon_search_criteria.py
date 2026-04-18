"""submit_coupon_search_criteria：搜优惠场景专用的"登记找优惠条件"工具。

两个 typed 参数（LLM 接口层）：
- activity_search_info: 活动本身维度（项目关键词、优惠类型、品牌等）
- shop_search_info: 商户维度（位置、商户类型、评分等——和 searchshops 完全一致）

**只写一个 ai_inputs 字段 `coupon_search_info`**，把两维度作为子对象装进去。
对 workflow 侧 validate_base 只需监听这一个字段（和 searchshops 的
shop_search_info 对称）。workflow 读 state 时用 `info.get("activity")` /
`info.get("shop")` 取各维度。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.tools._submit_helper import submit_workflow_fields
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("submit_coupon_search_criteria")


async def submit_coupon_search_criteria(
    ctx: RunContext[AgentDeps],
    activity_search_info: Annotated[dict[str, Any] | None, Field(
        description=(
            "活动本身维度的找优惠条件整包 JSON。结构（limit / query 根字段 + "
            "LEAF.params 可用字段）以当前步骤 instruction 里的 ACTIVITY_SEARCH_FIELDS "
            "为准，不要从这里推测。用户只提到商户维度时传 null。"
        )
    )] = None,
    shop_search_info: Annotated[dict[str, Any] | None, Field(
        description=(
            "商户维度的找店条件整包 JSON（orderBy / limit / query 三根字段）。"
            "结构和搜商户场景一致，以 instruction 里的 SHOP_SEARCH_FIELDS 为准，"
            "不要从这里推测。用户只提到活动维度时传 null。"
        )
    )] = None,
) -> str:
    """登记找优惠条件。"""
    if not activity_search_info and not shop_search_info:
        return "本次未提交任何字段，已忽略。"

    # 两个维度合并成单个 ai_inputs 字段，对称 shop_search_info 的设计
    coupon_search_info: dict[str, Any] = {}
    if activity_search_info:
        coupon_search_info["activity"] = activity_search_info
    if shop_search_info:
        coupon_search_info["shop"] = shop_search_info

    return await submit_workflow_fields(
        ctx,
        {"coupon_search_info": coupon_search_info},
        tool_name="submit_coupon_search_criteria",
        detail_type="search_coupons",
    )


submit_coupon_search_criteria.__doc__ = _DESCRIPTION

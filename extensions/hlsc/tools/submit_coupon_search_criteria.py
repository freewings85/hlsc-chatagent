"""submit_coupon_search_criteria：搜优惠活动场景专用的"登记找优惠活动条件"工具。

**扁平版 schema**（test/flat-coupon-schema 分支）：
不再分 activity / shop 两维度；LLM 只抽一棵 query 树，LEAF.params 合并所有字段。
后端 resolver 按字段名自动拆成 activity_query + shop_query。

好处：LLM 不再做"这个词归哪个维度"的跨维度决策，同名字段（project_keywords）歧义消除。
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
    coupon_search_info: Annotated[dict[str, Any] | None, Field(
        description=(
            "找优惠活动条件整包 JSON（orderBy / limit / query 根字段）。"
            "单一扁平 query 树，LEAF.params 同时容纳位置、商户、项目、活动类型等字段。"
            "结构和字段语义以当前步骤 instruction 里的 COUPON_SEARCH_FIELDS 为准，"
            "不要从这里推测。query 缺失则不调用。"
        )
    )] = None,
) -> str:
    """登记找优惠活动条件。"""
    if not coupon_search_info or not coupon_search_info.get("query"):
        return "本次未提交任何字段，已忽略。"

    return await submit_workflow_fields(
        ctx,
        {"coupon_search_info": coupon_search_info},
        tool_name="submit_coupon_search_criteria",
        detail_type="search_coupons",
    )


submit_coupon_search_criteria.__doc__ = _DESCRIPTION

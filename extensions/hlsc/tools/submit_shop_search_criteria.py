"""submit_shop_search_criteria：搜商户场景专用的"登记找店条件"工具。

typed 参数 = ShopSearchInfo Pydantic 模型。schema 通过 JSON Schema 暴露给 LLM
（tool-calling 阶段），instruction 层不再描述字段名和枚举值，避免对用户泄漏内部术语。

这个工具 = update_workflow_state 的场景化包装：LLM 只在 searchshops / debug
（searchshops 沙盒）场景下看到它，名字 + 描述直接锚定用途，减少字段幻觉。

提交后 workflow 会：
  1. 写入 ai_inputs.shop_search_info（model_dump by_alias 保留 orderBy 驼峰）
  2. resolve_and_search 构 API query → 写 own_fields.shop_complex_query
  3. execute_shop_complex_query 调 complexQuery → Goto(END, tool_result_raw=商户列表)

tool 返回给 LLM 的是 tool_result_message（如"找到 3 家商户"），商户详情通过
TOOL_RESULT_DETAIL 事件直接推前端，LLM 不直接消费。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.models.shop_search import ShopSearchInfo
from hlsc.tools._submit_helper import submit_workflow_fields
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("submit_shop_search_criteria")


async def submit_shop_search_criteria(
    ctx: RunContext[AgentDeps],
    shop_search_info: Annotated[ShopSearchInfo, Field(
        description=(
            "找店条件整包。按当前对话里用户原话里明确说过的条件填；"
            "没说过的字段一律省略（不要传空串、不要照 description 回填）。"
        )
    )],
) -> str:
    """登记找店条件。"""
    payload: dict = shop_search_info.model_dump(by_alias=True, exclude_none=True)
    if not payload.get("query"):
        return "本次未提交任何字段，已忽略。"
    return await submit_workflow_fields(
        ctx,
        {"shop_search_info": payload},
        tool_name="submit_shop_search_criteria",
        detail_type="search_repair_shops",
    )


submit_shop_search_criteria.__doc__ = _DESCRIPTION

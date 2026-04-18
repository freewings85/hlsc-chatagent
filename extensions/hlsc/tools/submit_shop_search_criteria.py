"""submit_shop_search_criteria：搜商户场景专用的"登记找店条件"工具。

typed 参数 = 一个 `shop_search_info` dict（结构见 workflow activity 里
SHOP_SEARCH_FIELDS 规范：orderBy / limit / query 三根字段 + 查询树）。

这个工具 = update_workflow_state 的场景化包装：LLM 只在 searchshops / debug
（searchshops 沙盒）场景下看到它，名字 + 描述直接锚定用途，减少字段幻觉。

提交后 workflow 会：
  1. 写入 ai_inputs.shop_search_info
  2. resolve_and_search 构 API query → 写 own_fields.shop_complex_query
  3. execute_shop_complex_query 调 complexQuery → Goto(END, tool_result_raw=商户列表)

tool 返回给 LLM 的是 tool_result_message（如"找到 3 家商户"），商户详情通过
TOOL_RESULT_DETAIL 事件直接推前端，LLM 不直接消费。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.tools._submit_helper import submit_workflow_fields
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("submit_shop_search_criteria")


async def submit_shop_search_criteria(
    ctx: RunContext[AgentDeps],
    shop_search_info: Annotated[dict[str, Any], Field(
        description=(
            "找店条件整包 JSON：\n"
            "- orderBy: 可选排序，取值 distance / rating / tradingCount\n"
            "- limit: 可选返回数量上限（整数）\n"
            "- query: 查询树（必填）。三种 op：\n"
            "    LEAF  params 放叶子条件，可用字段：\n"
            "      shop_type(str) / shop_name(str) / address(str) / city(str)\n"
            "      min_rating(1-5) / has_activity(bool) / radius(米，整数)\n"
            "      project_keywords(list[str]) / equipment_keywords(list[str])\n"
            "      fuzzy_keywords(list[str]，不放城市/地址/商户名/项目名)\n"
            "    AND   children 全部命中\n"
            "    OR    children 任一命中\n"
            "示例：{\"query\": {\"op\": \"LEAF\", \"params\": {\"shop_type\": \"4S店\", \"city\": \"上海\"}}}"
        )
    )],
) -> str:
    """登记找店条件。"""
    return await submit_workflow_fields(
        ctx,
        {"shop_search_info": shop_search_info},
        tool_name="submit_shop_search_criteria",
    )


submit_shop_search_criteria.__doc__ = _DESCRIPTION

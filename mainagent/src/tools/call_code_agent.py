"""call_code_agent 工具：通过 A2A 协议调用 CodeAgent subagent。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent

from src.config import CODE_AGENT_URL


async def call_code_agent(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """通过编程查询业务系统数据，回答复杂问题。

    适用场景 — 当用户的问题需要以下能力时应调用此工具：
    - 跨系统数据查询："张三上个月一共修了几次车？花了多少钱？"
    - 统计分析："这个月工单量比上个月多了多少？"
    - 排名对比："哪个门店的工单量最多？"
    - 复杂筛选："帮我找出所有超过3000元的未完成工单"
    - 库存查询："博世刹车片还有多少库存？"

    不适用：简单问答、闲聊、意见咨询等不需要查数据的问题。

    Args:
        query: 用户的数据查询需求，用自然语言描述。

    Returns:
        查询结果的自然语言描述。
    """
    return await call_subagent(ctx, url=CODE_AGENT_URL, message=query)

"""call_diagnose_agent 工具：通过 A2A 调用诊断 subagent。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent

from src.config import DIAGNOSE_AGENT_URL


async def call_diagnose_agent(
    ctx: RunContext[AgentDeps],
    query: Annotated[str, Field(description="包含车型信息和故障描述的完整查询")],
) -> str:
    """调用诊断 Agent 分析汽车故障原因。

    适用场景：
    - 用户描述故障症状："过减速带咚咚响"、"方向盘抖"、"发动机故障灯亮"
    - 用户指出故障部件："减震器坏了"、"刹车异响"
    - 需要专业诊断分析的复杂问题

    query 应包含车型信息（如 car_model_id）和故障描述。

    不适用：简单的服务查询（如"洗车多少钱"）、价格比较等。
    """
    return await call_subagent(ctx, url=DIAGNOSE_AGENT_URL, message=query)

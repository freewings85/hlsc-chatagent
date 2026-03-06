"""Agent Loop：手动 iter/next 驱动的核心循环"""

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.agent import ModelRequestNode, CallToolsNode
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.toolsets._dynamic import DynamicToolset
from pydantic_graph import End

from src.agent.deps import AgentDeps
from src.agent.toolset import get_tools


@dataclass
class AgentResult:
    """Agent 运行结果"""

    output: str
    nodes: list[str]
    tool_call_count: int
    messages: list[ModelMessage]


def create_agent(
    model: Model,
    system_prompt: str = "你是一个通用助手。",
    history_processors: list[Any] | None = None,
) -> Agent[AgentDeps, str]:
    """创建 Agent 实例"""
    return Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=system_prompt,
        toolsets=[DynamicToolset(get_tools, per_run_step=True)],
        history_processors=history_processors or [],
    )


async def run_agent_loop(
    agent: Agent[AgentDeps, str],
    user_input: str,
    deps: AgentDeps,
    message_history: list[ModelMessage] | None = None,
    max_iterations: int = 25,
) -> AgentResult:
    """手动驱动 agent loop"""
    nodes_log: list[str] = []
    iteration: int = 0

    async with agent.iter(
        user_input,
        deps=deps,
        message_history=message_history,
    ) as run:
        node = run.next_node

        while not isinstance(node, End):
            node_name: str = type(node).__name__
            nodes_log.append(node_name)

            if isinstance(node, ModelRequestNode):
                # 调 LLM 前：可在此修改 deps
                pass

            elif isinstance(node, CallToolsNode):
                # LLM 返回后：可在此观察响应
                pass

            node = await run.next(node)

            iteration += 1
            if iteration >= max_iterations:
                break

        nodes_log.append("End")

    output: str = run.result.output if run.result else ""
    all_messages: list[ModelMessage] = run.all_messages()

    return AgentResult(
        output=output,
        nodes=nodes_log,
        tool_call_count=deps.tool_call_count,
        messages=all_messages,
    )

"""DynamicToolset：每步从 deps 读取工具集"""

from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from src.agent.deps import AgentDeps


def get_tools(ctx: RunContext[AgentDeps]) -> FunctionToolset:
    """根据 deps.available_tools 和 deps.tool_map 构建当前步的工具集"""
    toolset: FunctionToolset = FunctionToolset()
    for name in ctx.deps.available_tools:
        func = ctx.deps.tool_map.get(name)
        if func is not None:
            toolset.add_tool(Tool(func, name=name))
    return toolset

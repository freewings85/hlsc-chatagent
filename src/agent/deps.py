"""AgentDeps：Agent 的依赖对象，所有状态通过此对象传递"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

# tool 函数类型：async def fn(ctx: RunContext[AgentDeps], ...) -> str
ToolFunc = Callable[..., Coroutine[Any, Any, str]]


@dataclass
class AgentDeps:
    """Agent 运行时依赖，通过 RunContext[AgentDeps] 在 tool 中访问"""

    session_id: str = "default"
    user_id: str = "anonymous"
    # 当前可用工具名列表
    available_tools: list[str] = field(default_factory=list)
    # tool 名 → 实现函数映射（eval 时可替换）
    tool_map: dict[str, ToolFunc] = field(default_factory=dict)
    # tool 执行过程中可修改的状态
    tool_call_count: int = 0
    last_tool_result: str = ""

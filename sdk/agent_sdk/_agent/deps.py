"""AgentDeps：Agent 的依赖对象，所有状态通过此对象传递"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from agent_sdk._agent.file_state import FileStateTracker
from agent_sdk._common.filesystem_backend import BackendProtocol

if TYPE_CHECKING:
    from temporalio.client import Client as TemporalClient

    from agent_sdk._agent.skills.invoked_store import InvokedSkillStore
    from agent_sdk._agent.skills.registry import SkillRegistry
    from agent_sdk._common.request_context import RequestContext
    from agent_sdk._event.event_emitter import EventEmitter

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
    # 文件系统后端（None 时工具内部 fallback 到 get_backend()）
    backend: BackendProtocol | None = None
    # 文件读写状态追踪（用于 changed_files attachment）
    file_state_tracker: FileStateTracker = field(default_factory=FileStateTracker)
    # Skill 系统（None 时 Skill 工具不可用）
    skill_registry: SkillRegistry | None = None
    invoked_skill_store: InvokedSkillStore | None = None
    # 事件发射器（interrupt 等工具需要直接发出 SSE 事件）
    emitter: EventEmitter | None = None
    # Skill 环境变量（invoke_skill 从 config.env 加载，bash 执行时注入）
    skill_env: dict[str, str] = field(default_factory=dict)
    # 请求上下文（位置、车辆信息等），工具可通过 ctx.deps.request_context 读取
    request_context: RequestContext | None = None
    # Temporal client（ask_user interrupt 机制用，必须配置）
    temporal_client: TemporalClient | None = None

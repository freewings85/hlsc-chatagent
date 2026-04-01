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
    request_id: str = ""
    user_id: str = "anonymous"
    # 当前可用工具名列表
    available_tools: list[str] = field(default_factory=list)
    # tool 名 → 实现函数映射（eval 时可替换）
    tool_map: dict[str, ToolFunc] = field(default_factory=dict)
    # tool 执行过程中可修改的状态
    tool_call_count: int = 0
    last_tool_result: str = ""
    # SDK 内部存储（消息、transcript、memory、skill store）
    # root: data/inner/{user}/sessions/{session}/
    inner_storage_backend: BackendProtocol | None = None
    # fs 工具（read/write/edit/bash/glob/grep）用的后端
    # mainagent: data/fstools/{user}/sessions/{session}/（用户隔离）
    # subagent: .（项目目录，可读 apis/ 等）
    fs_tools_backend: BackendProtocol | None = None
    # 文件读写状态追踪（用于 changed_files attachment）
    file_state_tracker: FileStateTracker = field(default_factory=FileStateTracker)
    # Skill 系统（None 时 Skill 工具不可用）
    skill_registry: SkillRegistry | None = None
    invoked_skill_store: InvokedSkillStore | None = None
    # 场景允许的 skill 名称列表（None 表示不限制，展示全部）
    allowed_skills: list[str] | None = None
    # 当前阶段标识（hook 设置，prompt loader 等可读取）
    current_stage: str = ""
    # 事件发射器（interrupt 等工具需要直接发出 SSE 事件）
    emitter: EventEmitter | None = None
    # 请求上下文（位置、车辆信息等），工具可通过 ctx.deps.request_context 读取
    request_context: RequestContext | None = None
    # Temporal client（call_interrupt 机制用，必须配置）
    temporal_client: TemporalClient | None = None
    # 即时切换：工具执行后设置，下次 ModelRequestNode 前替换 system prompt
    system_prompt_override: str | None = None

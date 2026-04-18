"""AgentDeps：Agent 的依赖对象，所有状态通过此对象传递"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from pydantic_ai.messages import ModelRequest, UserPromptPart

from agent_sdk._agent.file_state import FileStateTracker
from agent_sdk._common.filesystem_backend import BackendProtocol

if TYPE_CHECKING:
    from temporalio.client import Client as TemporalClient

    from agent_sdk._agent.memory.memory_message_service import MemoryMessageService
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
    # 同 turn 内相同 (tool_name, args_hash) 的调用计数——防 LLM 陷入重复调用死循环
    # 第 2 次短路返回陈述式合成 result；第 3 次及以上抛 AgentLoopError 终止本轮
    tool_call_dedup: dict[str, int] = field(default_factory=dict)
    # 本轮累计 tool 错误次数（由各工具在自己判断为失败时 += 1）+ 阈值
    # loop 每轮 tool node 结束后检查 count >= max_tool_errors → 硬停
    tool_error_count: int = 0
    max_tool_errors: int = 2
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
    # 事件发射器（interrupt 等工具需要直接发出 SSE 事件）
    emitter: EventEmitter | None = None
    # 请求上下文（位置、车辆信息等），工具可通过 ctx.deps.request_context 读取
    request_context: RequestContext | None = None
    # Temporal client（call_interrupt 机制用，必须配置）
    temporal_client: TemporalClient | None = None
    # 场景级 agent_md 文件名（由 hook 设置，prompt_loader 优先使用）
    current_scene_agent_md: str | None = None
    # 当前场景标识（hook 设置，prompt_loader 按场景加载 prompt）
    current_scene: str = "guide"
    # 会话级状态（project_id, shop_id 等已确认信息，跨轮次共享）
    session_state: dict[str, Any] = field(default_factory=dict)
    # session_state 对应的 context_message 占位引用（工具更新后刷新内容）
    _session_state_msg: ModelRequest | None = None
    # memory_service（由 agent.run 构建，供 hook 读取历史消息）
    memory_service: MemoryMessageService | None = None

    # ── Orchestrator 编排字段（可选，降级模式全部为 None/空）──
    # update_workflow_state 工具检测 workflow_id 非空 → 进入 orchestrator 模式
    workflow_id: str | None = None
    orchestrator_url: str | None = None
    # 当前 AICall 的 instruction 文本（业务方在 activity 里组织好，框架不解析）
    # PreRunHook 从 orchestrator context 解包，update_workflow_state 工具热切换
    instruction: str = ""
    # 场景中文名（如"保险竞价"），仅用于日志/观测
    scenario_label: str = ""


# ── session_state 辅助函数 ──


def format_session_state(state: dict[str, Any]) -> str:
    """将 session_state 格式化为注入 LLM 的文本。"""
    if not state:
        return "### session_state\n\n(空)"
    pairs: list[str] = [f"{k}={v}" for k, v in state.items() if v is not None]
    if not pairs:
        return "### session_state\n\n(空)"
    return "### session_state\n\n" + ", ".join(pairs)


def create_session_state_message(state: dict[str, Any]) -> ModelRequest:
    """创建 session_state 的 context_message（可被引用更新内容）。

    source 标识为 "session_state"，供 context_injector 识别。
    """
    return ModelRequest(
        parts=[UserPromptPart(content=format_session_state(state))],
        metadata={"is_meta": True, "source": "session_state"},
    )

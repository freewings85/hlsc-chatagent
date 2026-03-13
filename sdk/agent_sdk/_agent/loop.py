"""Agent Loop：手动 iter/next 驱动的核心循环，通过 EventEmitter 发出事件

三层架构：
- run_main_agent()  — 主 agent 入口，构建完整 services 后调用 run_agent_loop
- run_agent_loop()  — 核心引擎（纯循环），不做任何初始化决策
- run_sub_agent()   — 子 agent 入口（Phase 2 实现）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.agent import ModelRequestNode, CallToolsNode
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets._dynamic import DynamicToolset
from pydantic_graph import End

from agent_sdk._utils.request_context import clear_request_context, set_request_context
from agent_sdk._utils.session_logger import (
    log_error,
    log_info,
    log_llm_end,
    log_llm_start,
    log_request_end,
    log_request_start,
    log_tool_end,
    log_tool_start,
)

from agent_sdk._agent.agent_message import (
    AgentMessage,
    UserMessage,
    from_model_messages,
    to_model_messages,
    validate_message_alternation,
)
from agent_sdk._agent.compact.compactor import Compactor, SummarizeFn
from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.message.attachment_collector import AttachmentCollector
from agent_sdk._agent.memory.memory_context_service import MemoryContextService
from agent_sdk._agent.memory.memory_message_service import MemoryMessageService
from agent_sdk._agent.message.pre_model_call_service import PreModelCallMessageService
from agent_sdk._agent.message.transcript_service import TranscriptService
from agent_sdk._agent.prompt.prompt_builder import PromptBuilder
from agent_sdk._agent.skills.invoked_store import InvokedSkillStore
from agent_sdk._agent.skills.registry import SkillRegistry, get_default_skill_dirs
from agent_sdk._agent.skills.tool import invoke_skill
from agent_sdk._agent.mcp.loader import load_mcp_toolsets
from agent_sdk._agent.toolset import get_tools
from agent_sdk._common.session_request_task import SessionRequestTask
from agent_sdk._config.settings import (
    get_agent_fs_backend,
    get_backend,
    get_compact_config,
    get_memory_context_service,
    get_memory_message_service,
    get_transcript_service,
)
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._agent.card_parser import make_card_reminder, parse_card
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


# ── LoopContext ────────────────────────────────────────────────────────────


@dataclass
class LoopContext:
    """run_agent_loop 所需的全部依赖，由 run_main_agent / run_sub_agent 构建。"""

    # 核心
    agent: Agent[AgentDeps, str]
    deps: AgentDeps
    emitter: EventEmitter
    task: SessionRequestTask

    # 消息服务
    pre_call_service: PreModelCallMessageService
    memory_service: MemoryMessageService
    transcript_service: TranscriptService

    # 历史
    agent_history: list[AgentMessage] = field(default_factory=list)

    # MCP
    mcp_toolsets: list[AbstractToolset[Any]] | None = None

    # 运行限制
    max_iterations: int = 25

    # 子 agent 标识（用于事件的 agent_name 字段）
    agent_name: str = "main"

    # 子 agent 模式：不管理 request_context，不发 CHAT_REQUEST_END，不关闭 emitter
    is_sub_agent: bool = False

    # transcript 存储路径的 session_id（子 agent 隔离用）。None → 用 task.session_id
    transcript_session_id: str | None = None


# ── Agent 工厂 ─────────────────────────────────────────────────────────────


def create_agent(
    model: Model,
    history_processors: list[Any] | None = None,
    system_prompt: str | None = None,
) -> Agent[AgentDeps, str]:
    """创建 Agent 实例。

    Args:
        model: LLM 模型
        history_processors: 消息历史处理器
        system_prompt: 可选的 system prompt（subagent 场景）。
            main agent 由 PreModelCallMessageService 注入，不需要此参数。
    """
    kwargs: dict[str, Any] = {
        "deps_type": AgentDeps,
        "toolsets": [DynamicToolset(get_tools, per_run_step=True)],
        "history_processors": history_processors or [],
    }
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    return Agent(model, **kwargs)


# ── 辅助函数 ───────────────────────────────────────────────────────────────


def _make_summarize_fn(agent: Agent[AgentDeps, str]) -> SummarizeFn:
    """创建用于 full compact 的 LLM 摘要回调。

    使用同一个 agent 的模型，以简单 prompt 生成对话摘要。
    """
    async def summarize_fn(messages: list[ModelMessage]) -> str:
        history_text = _format_messages_for_summary(messages)
        prompt = (
            "请将以下对话历史压缩为一段简洁的摘要，保留关键信息、决策和上下文，"
            "使后续对话能在此基础上继续。\n\n"
            f"对话历史：\n{history_text}"
        )
        result = await agent.run(prompt)
        return result.output

    return summarize_fn


def _format_messages_for_summary(messages: list[ModelMessage]) -> str:
    """将消息列表格式化为可读文本（用于摘要 prompt）。"""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    lines.append(f"用户: {part.content[:500]}")
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    lines.append(f"助手: {part.content[:500]}")
    return "\n".join(lines)


# ── 流式事件发射 ───────────────────────────────────────────────────────────


async def _emit_model_stream(
    node: ModelRequestNode[AgentDeps, str],
    ctx: Any,
    emitter: EventEmitter,
    task: SessionRequestTask,
    messages_count: int = 0,
    messages: list[ModelMessage] | None = None,
    user_prompt: str | None = None,
    agent_name: str = "main",
) -> None:
    """流式消费 ModelRequestNode，逐 token 发出 TEXT / TOOL_CALL 事件。

    stream 结束后 node._result 已设置，后续 run.next(node) 不会重复调 LLM。
    """
    log_llm_start(
        "ModelRequestNode",
        messages_count=messages_count,
        messages=messages,
        user_prompt=user_prompt,
    )

    _text_parts: list[str] = []
    _tool_call_names: list[str] = []

    async with node.stream(ctx) as agent_stream:
        async for event in agent_stream:
            if isinstance(event, PartStartEvent):
                part = event.part
                if isinstance(part, TextPart) and part.content:
                    _text_parts.append(part.content)
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TEXT,
                        data={"content": part.content},
                        agent_name=agent_name,
                    ))
                elif isinstance(part, ToolCallPart):
                    _tool_call_names.append(part.tool_name)
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_CALL_START,
                        data={
                            "tool_name": part.tool_name,
                            "tool_call_id": part.tool_call_id or "",
                        },
                        agent_name=agent_name,
                    ))
            elif isinstance(event, PartDeltaEvent):
                delta = event.delta
                if isinstance(delta, TextPartDelta):
                    _text_parts.append(delta.content_delta)
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TEXT,
                        data={"content": delta.content_delta},
                        agent_name=agent_name,
                    ))
                elif isinstance(delta, ToolCallPartDelta):  # pragma: no cover — 真实 LLM 流式 tool call 才触发
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_CALL_ARGS,
                        data={"args_chunk": delta.args_delta},
                        agent_name=agent_name,
                    ))

    # LLM 响应完成后记录日志
    if _tool_call_names:
        log_llm_end("ModelRequestNode", tool_calls=_tool_call_names)
    else:
        log_llm_end("ModelRequestNode", response_preview="".join(_text_parts))


async def _emit_tool_events(
    node: CallToolsNode[AgentDeps, str],
    ctx: Any,
    emitter: EventEmitter,
    task: SessionRequestTask,
    agent_name: str = "main",
) -> None:
    """流式消费 CallToolsNode，发出 TOOL_CALL_START / TOOL_RESULT 事件。

    stream 结束后 node._next_node 已设置，后续 run.next(node) 不会重复执行工具。
    """
    async with node.stream(ctx) as event_stream:
        async for event in event_stream:
            if isinstance(event, FunctionToolCallEvent):
                # TOOL_CALL_START 已由 _emit_model_stream 中的 PartStartEvent(ToolCallPart) 发出
                # 此处不重复发送，避免前端创建两个相同 tool_call_id 的工具块
                tool_name = event.part.tool_name if event.part else "unknown"
                log_tool_start(tool_name)
            elif isinstance(event, FunctionToolResultEvent):
                content = event.result.content if hasattr(event.result, "content") else str(event.result)
                result_tool_name = event.result.tool_name
                tool_call_id = getattr(event.result, "tool_call_id", "")
                log_tool_end(result_tool_name, output_data=content)

                # 卡片解析：从 tool result 中提取 <!--card:type--> 块
                # MCP tool 返回的 content 可能是 dict {"result": "..."}, 需提取字符串
                card_text = content
                if isinstance(content, dict) and "result" in content:
                    card_text = str(content["result"])
                elif not isinstance(content, str):
                    card_text = str(content)
                card = parse_card(card_text)
                if card and tool_call_id:
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_RESULT_DETAIL,
                        data={
                            "tool_call_id": tool_call_id,
                            "detail_type": card.card_type,
                            "data": {"success": True, "data": card.data},
                        },
                        agent_name=agent_name,
                    ))
                    # 追加 system-reminder 提示 LLM 可以引用卡片
                    reminder = make_card_reminder(tool_call_id)
                    if isinstance(content, dict) and "result" in content:
                        content = {**content, "result": str(content["result"]) + reminder}
                    elif isinstance(content, str):
                        content = content + reminder
                    else:
                        content = str(content) + reminder
                    # 修改 tool result content 以便 LLM 看到 reminder
                    if hasattr(event.result, "content"):
                        event.result.content = content

                await emitter.emit(EventModel(
                    session_id=task.session_id,
                    request_id=task.request_id,
                    type=EventType.TOOL_RESULT,
                    data={
                        "tool_name": result_tool_name,
                        "tool_call_id": tool_call_id,
                        "result": content,
                    },
                    agent_name=agent_name,
                ))


# ── 核心引擎 ───────────────────────────────────────────────────────────────


async def run_agent_loop(ctx: LoopContext) -> str | None:
    """核心引擎：iter/next 循环 + 流式事件 + compact + 持久化。

    不做任何初始化决策，只消费 LoopContext 中构建好的 services。
    返回 final_response 文本（或 None）。
    """
    agent = ctx.agent
    deps = ctx.deps
    emitter = ctx.emitter
    task = ctx.task
    pre_call_service = ctx.pre_call_service
    memory_service = ctx.memory_service
    transcript_service = ctx.transcript_service
    agent_history = ctx.agent_history
    mcp_toolsets = ctx.mcp_toolsets
    max_iterations = ctx.max_iterations
    agent_name = ctx.agent_name
    is_sub_agent = ctx.is_sub_agent
    _transcript_sid = ctx.transcript_session_id or task.session_id

    # 请求上下文：子 agent 不管理（父 agent 已设置）
    if not is_sub_agent:
        set_request_context(task.session_id, task.request_id)
    log_request_start(
        session_id=task.session_id,
        user_query=task.message,
        user_id=task.user_id,
        request_id=task.request_id,
    )

    try:
        iteration: int = 0
        _base_len: int = 0
        _first_llm_call: bool = True

        async with agent.iter(
            task.message,
            deps=deps,
            message_history=[],  # 空历史，由我们在 ModelRequestNode 前注入
            toolsets=mcp_toolsets if mcp_toolsets else None,
        ) as run:
            node = run.next_node

            while not isinstance(node, End):
                if task.cancelled:
                    break

                if isinstance(node, ModelRequestNode):
                    if _first_llm_call:
                        # 首次 LLM 调用：将 AgentMessage 历史转为 ModelMessage 注入
                        # 追加当前用户消息，使 to_model_messages 能校验交替 + 最后为 user
                        full_session = list(agent_history) + [
                            UserMessage(content=task.message),
                        ]
                        model_messages = to_model_messages(full_session)
                        # 去掉最后一个 ModelRequest（当前用户消息），Pydantic AI 会自动追加
                        run._graph_run.state.message_history[:] = model_messages[:-1] if model_messages else []

                    history: list[ModelMessage] = run._graph_run.state.message_history

                    # 每轮 LLM 前：context injection + attachment + compact
                    pre_result = await pre_call_service.handle(history)

                    # 若 compact 发生，转换为 AgentMessage 后更新工作集
                    if pre_result.compacted:
                        log_info(f"[COMPACT] iteration={iteration}")
                        agent_working = from_model_messages(pre_result.working_messages)
                        await memory_service.update(
                            task.user_id, task.session_id, agent_working,
                        )
                        deps.file_state_tracker.clear()

                    if _base_len == 0:
                        _base_len = len(pre_result.model_messages)

                    # 注入处理后的消息到 run 内部状态
                    run._graph_run.state.message_history[:] = pre_result.model_messages

                    # 校验消息交替（所有处理完成后、模型调用前）
                    # Pydantic AI _prepare_request() 会追加 user turn：
                    # - 首次调用：追加 UserPromptPart（用户原始消息）
                    # - 后续调用：追加 ToolReturnPart（工具返回结果）
                    # 此处用 pending_user 告知校验器"将会有一个 user turn 被追加"
                    if _first_llm_call:
                        pending_user: str | None = task.message
                    else:
                        last_msg = pre_result.model_messages[-1] if pre_result.model_messages else None
                        pending_user = "__tool_return__" if isinstance(last_msg, ModelResponse) else None
                    alt_errors = validate_message_alternation(
                        pre_result.model_messages,
                        user_prompt=pending_user,
                    )
                    if alt_errors:
                        log_error(
                            f"[MSG_ALTERNATION] 消息交替校验失败 "
                            f"(iteration={iteration}): {alt_errors}"
                        )

                    # 流式处理 LLM 响应（node.stream 内部完成 LLM 调用并缓存结果）
                    await _emit_model_stream(
                        node, run.ctx, emitter, task,
                        messages_count=len(pre_result.model_messages),
                        messages=pre_result.model_messages,
                        user_prompt=task.message if _first_llm_call else None,
                        agent_name=agent_name,
                    )
                    _first_llm_call = False
                    # stream 已完成，next() 只做状态转移（不会重复调 LLM）
                    node = await run.next(node)

                elif isinstance(node, CallToolsNode):
                    # 工具执行（node.stream 内部完成工具调用并缓存结果）
                    await _emit_tool_events(node, run.ctx, emitter, task, agent_name=agent_name)
                    # stream 已完成，next() 只做状态转移（不会重复执行工具）
                    node = await run.next(node)

                else:
                    # 未知 node 类型，直接推进
                    node = await run.next(node)

                iteration += 1
                if iteration >= max_iterations:
                    break

        # 持久化新消息：ModelMessage → AgentMessage，写 messages.jsonl 和 transcript.jsonl
        # offset = _base_len：跳过 context + 已持久化历史（user prompt 在 _base_len 之后
        # 由 _prepare_request 追加，不包含在 _base_len 中）
        # 注意：持久化在 CHAT_REQUEST_END 之前，确保客户端收到结束事件时数据已落盘
        final_response: str | None = None
        if run.result is not None:
            final_response = run.result.output
            new_messages: list[ModelMessage] = run.result.all_messages()
            appended = new_messages[_base_len:]
            # 转换为 AgentMessage 后持久化
            new_agent_messages = from_model_messages(appended)
            await transcript_service.append(task.user_id, _transcript_sid, new_agent_messages)
            if not is_sub_agent:
                # 子 agent 不写 messages.jsonl（fresh context，无需工作集持久化）
                await memory_service.insert_batch(task.user_id, task.session_id, new_agent_messages)

    except Exception as exc:
        log_error(f"Agent loop 异常 (agent={agent_name}): {exc}", exc=exc)
        log_request_end(
            session_id=task.session_id,
            success=False,
            error=str(exc),
            request_id=task.request_id,
        )
        # 发送错误事件通知客户端
        await emitter.emit(EventModel(
            session_id=task.session_id,
            request_id=task.request_id,
            type=EventType.ERROR,
            data={"message": str(exc)},
            agent_name=agent_name,
        ))
        raise
    else:
        log_request_end(
            session_id=task.session_id,
            success=True,
            request_id=task.request_id,
            response=final_response,
        )
    finally:
        if not is_sub_agent:
            clear_request_context()
            # 发送 chat_request_end 事件，通知前端流结束
            await emitter.emit(EventModel(
                session_id=task.session_id,
                request_id=task.request_id,
                type=EventType.CHAT_REQUEST_END,
                data={},
                agent_name=agent_name,
            ))
            await emitter.close()

    return final_response


# ── 主 Agent 入口 ──────────────────────────────────────────────────────────


async def run_main_agent(
    emitter: EventEmitter,
    task: SessionRequestTask,
    agent: Agent[AgentDeps, str],
    deps: AgentDeps,
    message_history: list[ModelMessage] | None = None,
    max_iterations: int = 25,
) -> None:
    """主 Agent 入口。保持现有 API 签名不变（app.py / task_worker.py 不用改）。

    负责：
    1. 设置 backend + request_context
    2. 构建 PromptBuilder → context_messages
    3. 构建 Skill 系统 → 注入 deps
    4. 构建 PreModelCallMessageService
    5. 加载 MCP toolsets
    6. 加载历史（MemoryMessageService）
    7. 组装 LoopContext
    8. 调用 run_agent_loop(ctx)
    """
    # 确保 deps 与 task 的 session/user 信息一致
    deps.session_id = task.session_id
    deps.user_id = task.user_id

    backend = get_backend()
    agent_fs_backend = get_agent_fs_backend()

    # 工具的工作目录 = session 目录（write("plan.md") → data/{user_id}/sessions/{session_id}/plan.md）
    from agent_sdk._storage.local_backend import FilesystemBackend
    from agent_sdk._config.settings import get_user_fs_config
    _user_fs_cfg = get_user_fs_config()
    _session_root = f"{_user_fs_cfg.user_fs_dir}/{task.user_id}/sessions/{task.session_id}"
    deps.backend = FilesystemBackend(root_dir=_session_root, virtual_mode=True)
    deps.emitter = emitter

    # 服务获取（全局单例，跨 request 复用缓存）
    memory_service = get_memory_message_service()
    context_service = get_memory_context_service()
    transcript_service = get_transcript_service()
    prompt_builder: PromptBuilder = PromptBuilder(
        user_fs_backend=backend,
    )
    context_messages: list[ModelRequest] = await prompt_builder.build_context_messages(
        user_id=task.user_id,
    )

    # 请求上下文 diff：只在有变化时注入消息，同时更新 deps 供工具读取
    if task.context is not None:
        changed = await context_service.diff(task.user_id, task.session_id, task.context)
        if changed:
            context_text = context_service.format_changed(changed)
            context_messages.append(ModelRequest(
                parts=[UserPromptPart(content=context_text)],
                metadata={"is_meta": True, "source": "request_context"},
            ))
        await context_service.set(task.user_id, task.session_id, task.context)
        deps.request_context = task.context
    attachment_collector = AttachmentCollector(deps.file_state_tracker)
    compactor = Compactor(
        config=get_compact_config(),
        user_id=task.user_id,
        session_id=task.session_id,
        summarize_fn=_make_summarize_fn(agent),
    )

    # Skill 系统初始化
    skill_registry = SkillRegistry.load(get_default_skill_dirs())
    invoked_store = InvokedSkillStore(backend, task.user_id, task.session_id)
    await invoked_store.load()

    # 若有可用 skill，注册 Skill 工具到 deps
    if skill_registry.has_skills():
        deps.skill_registry = skill_registry
        deps.invoked_skill_store = invoked_store
        deps.available_tools = [t for t in deps.available_tools if t != "Skill"] + ["Skill"]
        deps.tool_map["Skill"] = invoke_skill  # type: ignore[assignment]

    system_prompt = PromptBuilder.load_system_prompt()
    pre_call_service = PreModelCallMessageService(
        compactor=compactor,
        context_messages=context_messages,
        attachment_collector=attachment_collector,
        skill_registry=skill_registry if skill_registry.has_skills() else None,
        invoked_skill_store=invoked_store if skill_registry.has_skills() else None,
        system_prompt=system_prompt,
    )

    # MCP toolsets 动态加载（每次对话获取最新配置）
    mcp_toolsets = await load_mcp_toolsets(agent_fs_backend)

    # 加载历史（保持 AgentMessage 格式，仅在 ModelRequestNode 执行前转换）
    agent_history: list[AgentMessage] = []
    if message_history is None:
        agent_history = await memory_service.load(task.user_id, task.session_id)
    else:
        # 兼容外部传入 ModelMessage 的场景（如测试）
        agent_history = from_model_messages(message_history)

    # 组装 LoopContext 并调用核心引擎
    ctx = LoopContext(
        agent=agent,
        deps=deps,
        emitter=emitter,
        task=task,
        pre_call_service=pre_call_service,
        memory_service=memory_service,
        transcript_service=transcript_service,
        agent_history=agent_history,
        mcp_toolsets=mcp_toolsets if mcp_toolsets else None,
        max_iterations=max_iterations,
        agent_name="main",
    )

    await run_agent_loop(ctx)

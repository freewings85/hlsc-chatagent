"""Agent Loop：手动 iter/next 驱动的核心循环，通过 EventEmitter 发出事件"""

from __future__ import annotations

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
)
from pydantic_ai.models import Model
from pydantic_ai.toolsets._dynamic import DynamicToolset
from pydantic_graph import End

from src.utils.request_context import clear_request_context, set_request_context
from src.utils.session_logger import (
    log_error,
    log_info,
    log_llm_end,
    log_llm_start,
    log_request_end,
    log_request_start,
    log_tool_end,
    log_tool_start,
)

from src.agent.agent_message import (
    AgentMessage,
    UserMessage,
    from_model_messages,
    to_model_messages,
    validate_message_alternation,
)
from src.agent.compact.compactor import Compactor, SummarizeFn
from src.agent.deps import AgentDeps
from src.agent.message.attachment_collector import AttachmentCollector
from src.agent.message.memory_message_service import MemoryMessageService
from src.agent.message.pre_model_call_service import PreModelCallMessageService
from src.agent.message.transcript_service import TranscriptService
from src.agent.prompt.prompt_builder import PromptBuilder
from src.agent.skills.invoked_store import InvokedSkillStore
from src.agent.skills.registry import SkillRegistry, get_default_skill_dirs
from src.agent.skills.tool import invoke_skill
from src.agent.mcp.loader import load_mcp_toolsets
from src.agent.toolset import get_tools
from src.common.session_request_task import SessionRequestTask
from src.config.settings import get_agent_fs_backend, get_backend, get_compact_config
from src.event.event_emitter import EventEmitter
from src.agent.card_parser import make_card_reminder, parse_card
from src.event.event_model import EventModel
from src.event.event_type import EventType


def create_agent(
    model: Model,
    history_processors: list[Any] | None = None,
) -> Agent[AgentDeps, str]:
    """创建 Agent 实例（system prompt 由 PreModelCallMessageService 注入）"""
    return Agent(
        model,
        deps_type=AgentDeps,
        toolsets=[DynamicToolset(get_tools, per_run_step=True)],
        history_processors=history_processors or [],
    )


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


async def _emit_model_stream(
    node: ModelRequestNode[AgentDeps, str],
    ctx: Any,
    emitter: EventEmitter,
    task: SessionRequestTask,
    messages_count: int = 0,
    messages: list[ModelMessage] | None = None,
    user_prompt: str | None = None,
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
                    ))
                elif isinstance(delta, ToolCallPartDelta):  # pragma: no cover — 真实 LLM 流式 tool call 才触发
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_CALL_ARGS,
                        data={"args_chunk": delta.args_delta},
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
                ))


async def run_agent_loop(
    emitter: EventEmitter,
    task: SessionRequestTask,
    agent: Agent[AgentDeps, str],
    deps: AgentDeps,
    message_history: list[ModelMessage] | None = None,
    max_iterations: int = 25,
) -> None:
    """手动驱动 agent loop，通过 emitter 发出事件。

    三层消息架构（参考设计文档 doc/agentloop主设计.md）：
    - MemoryMessageService  — 会话消息工作集（缓存 + messages.jsonl）
    - PreModelCallMessageService — 每轮 LLM 前：context + attachment + compact
    - TranscriptService     — append-only 审计日志（transcript.jsonl）

    流式事件：
    - ModelRequestNode: 通过 node.stream(ctx) 逐 token 发出 TEXT / TOOL_CALL 事件
    - CallToolsNode: 通过 node.stream(ctx) 发出 TOOL_RESULT 事件
    - stream 完成后 run.next(node) 不会重复执行（内部检查 _result/_next_node）
    """
    # 设置请求上下文（供 tool/service 层自动获取 session_id/request_id）
    set_request_context(task.session_id, task.request_id)
    log_request_start(
        session_id=task.session_id,
        user_query=task.message,
        user_id=task.user_id,
        request_id=task.request_id,
    )

    backend = get_backend()
    agent_fs_backend = get_agent_fs_backend()

    # 工具的工作目录 = session 目录（write("plan.md") → data/{user_id}/sessions/{session_id}/plan.md）
    from src.storage.local_backend import FilesystemBackend
    from src.config.settings import get_user_fs_config
    _user_fs_cfg = get_user_fs_config()
    _session_root = f"{_user_fs_cfg.user_fs_dir}/{task.user_id}/sessions/{task.session_id}"
    deps.backend = FilesystemBackend(root_dir=_session_root, virtual_mode=True)
    deps.emitter = emitter

    # 服务初始化
    memory_service = MemoryMessageService(backend)
    transcript_service = TranscriptService(backend)
    prompt_builder: PromptBuilder = PromptBuilder(
        user_fs_backend=backend,
        agent_fs_backend=agent_fs_backend,
    )
    context_messages: list[ModelRequest] = await prompt_builder.build_context_messages(
        user_id=task.user_id,
    )
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
                    )
                    _first_llm_call = False
                    # stream 已完成，next() 只做状态转移（不会重复调 LLM）
                    node = await run.next(node)

                elif isinstance(node, CallToolsNode):
                    # 工具执行（node.stream 内部完成工具调用并缓存结果）
                    await _emit_tool_events(node, run.ctx, emitter, task)
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
            await transcript_service.append(task.user_id, task.session_id, new_agent_messages)
            await memory_service.insert_batch(task.user_id, task.session_id, new_agent_messages)

    except Exception as exc:
        log_error(f"Agent loop 异常: {exc}", exc=exc)
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
        clear_request_context()
        # 发送 chat_request_end 事件，通知前端流结束
        await emitter.emit(EventModel(
            session_id=task.session_id,
            request_id=task.request_id,
            type=EventType.CHAT_REQUEST_END,
            data={},
        ))
        await emitter.close()

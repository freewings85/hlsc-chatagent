"""Agent Loop：手动 iter/next 驱动的核心循环，通过 EventEmitter 发出事件

三层架构：
- run_main_agent()  — 主 agent 入口，构建完整 services 后调用 run_agent_loop
- run_agent_loop()  — 核心引擎（纯循环），不做任何初始化决策
- run_sub_agent()   — 子 agent 入口（Phase 2 实现）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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

from agent_sdk.exceptions import AgentLoopError
from agent_sdk._utils.request_context import clear_request_context, set_request_context
from agent_sdk._utils.session_logger import (
    log_error,
    log_info,
    log_llm_end,
    log_llm_start,
    log_request_end,
    log_tool_end,
    log_tool_start,
)

from agent_sdk._agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    UserMessage,
    from_model_messages,
    to_model_messages,
    validate_message_alternation,
)
from agent_sdk._agent.compact.compactor import Compactor, SummarizeFn
from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.memory.memory_message_service import MemoryMessageService
from agent_sdk._agent.message.pre_model_call_service import PreModelCallMessageService
from agent_sdk._agent.message.transcript_service import TranscriptService
from agent_sdk._agent.toolset import get_tools
from agent_sdk._common.session_request_task import SessionRequestTask
from agent_sdk._config.settings import get_compact_config
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._agent.card_parser import make_card_reminder, parse_card
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


def _tag_request_phase(messages: list[AgentMessage], request_id: str) -> None:
    """为本次 request 产生的消息打上 request_id/request_phase。"""
    if not messages:
        return

    if len(messages) == 1:
        msg = messages[0]
        if isinstance(msg, (UserMessage, AssistantMessage)):
            msg.metadata["request_id"] = request_id
            msg.metadata["request_phase"] = "request_end"
        return

    last_idx = len(messages) - 1
    for idx, msg in enumerate(messages):
        if not isinstance(msg, (UserMessage, AssistantMessage)):
            continue
        msg.metadata["request_id"] = request_id
        if idx == 0:
            msg.metadata["request_phase"] = "request_start"
        elif idx == last_idx:
            msg.metadata["request_phase"] = "request_end"
        else:
            msg.metadata["request_phase"] = "request_inner"


FinishReason = Literal["completed", "cancelled", "max_iterations", "error"]


@dataclass
class RunLoopResult:
    """run_agent_loop 的统一返回结果。

    所有结束语义收敛于此，上层（hook / 前端事件 / 日志）统一消费。
    """

    final_response: str | None = None
    finish_reason: FinishReason = "completed"
    transcript_persisted: bool = False
    usage: dict[str, int] | None = None


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

    # 父工具调用 ID：子 agent 的事件携带此字段，前端据此分区渲染
    parent_tool_call_id: str | None = None

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

    使用无工具的轻量 Agent 避免摘要时意外触发工具调用。
    """
    from pydantic_ai import Agent as PydanticAgent

    # 创建无工具的摘要专用 agent，复用模型配置
    _summarize_agent: PydanticAgent[None, str] = PydanticAgent(
        model=agent.model,
        system_prompt="你是对话摘要助手。将对话历史压缩为简洁摘要，保留关键信息、决策和上下文。",
    )

    async def summarize_fn(messages: list[ModelMessage]) -> str:
        history_text: str = _format_messages_for_summary(messages)
        prompt: str = (
            "请将以下对话历史压缩为一段简洁的摘要，保留关键信息、决策和上下文，"
            "使后续对话能在此基础上继续。\n\n"
            f"对话历史：\n{history_text}"
        )
        result = await _summarize_agent.run(prompt)
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
    agent_name: str = "main",
    parent_tool_call_id: str | None = None,
) -> None:
    """流式消费 ModelRequestNode，逐 token 发出 TEXT / TOOL_CALL 事件。

    stream 结束后 node._result 已设置，后续 run.next(node) 不会重复调 LLM。
    日志在 node.stream(ctx) 进入后打印，此时 _prepare_request 已执行，
    ctx.state.message_history 是发给 LLM 的真实完整消息列表。
    """
    _text_parts: list[str] = []
    _tool_call_names: list[str] = []

    async with node.stream(ctx) as agent_stream:
        # _prepare_request 已执行，ctx.state.message_history 是真实发给 LLM 的消息
        actual_messages: list[ModelMessage] = ctx.state.message_history
        log_llm_start(
            "ModelRequestNode",
            messages_count=len(actual_messages),
            messages=actual_messages,
        )
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
                        parent_tool_call_id=parent_tool_call_id,
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
                        parent_tool_call_id=parent_tool_call_id,
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
                        parent_tool_call_id=parent_tool_call_id,
                    ))
                elif isinstance(delta, ToolCallPartDelta):  # pragma: no cover — 真实 LLM 流式 tool call 才触发
                    await emitter.emit(EventModel(
                        session_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_CALL_ARGS,
                        data={"tool_call_id": delta.tool_call_id, "args_chunk": delta.args_delta},
                        agent_name=agent_name,
                        parent_tool_call_id=parent_tool_call_id,
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
    parent_tool_call_id: str | None = None,
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
                tool_args: dict[str, Any] | None = None
                if event.part and event.part.args:
                    try:
                        tool_args = event.part.args if isinstance(event.part.args, dict) else __import__("json").loads(event.part.args)
                    except Exception:
                        tool_args = {"raw": str(event.part.args)[:500]}
                log_tool_start(tool_name, input_data=tool_args, session_id=task.session_id, request_id=task.request_id)
            elif isinstance(event, FunctionToolResultEvent):
                content = event.result.content if hasattr(event.result, "content") else str(event.result)
                result_tool_name = event.result.tool_name
                tool_call_id = getattr(event.result, "tool_call_id", "")
                log_tool_end(result_tool_name, output_data=content, session_id=task.session_id, request_id=task.request_id)

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
                        parent_tool_call_id=parent_tool_call_id,
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
                    parent_tool_call_id=parent_tool_call_id,
                ))


# ── 核心引擎 ───────────────────────────────────────────────────────────────


async def run_agent_loop(ctx: LoopContext) -> RunLoopResult:
    """核心引擎：iter/next 循环 + 流式事件 + compact + 持久化。

    不做任何初始化决策，只消费 LoopContext 中构建好的 services。
    返回 RunLoopResult，上层根据 finish_reason / transcript_persisted 统一决策。
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

    result = RunLoopResult()

    # 请求上下文：子 agent 不管理（父 agent 已设置）
    if not is_sub_agent:
        set_request_context(task.session_id, task.request_id)
    # 注意：log_request_start 已由 Agent._run_request 在 PreRunHook 之前调用，
    # 这样 PreRunHook / prompt_loader 阶段的失败也能落到 session 日志。这里不再重复

    try:
        iteration: int = 0
        _base_len: int = 0
        _first_llm_call: bool = True

        async with agent.iter(
            task.message,
            deps=deps,
            message_history=[],
            toolsets=mcp_toolsets if mcp_toolsets else None,
        ) as run:
            node = run.next_node

            while not isinstance(node, End):
                if task.cancelled:
                    result.finish_reason = "cancelled"
                    break

                if isinstance(node, ModelRequestNode):
                    if _first_llm_call:
                        full_session = list(agent_history) + [
                            UserMessage(content=task.message),
                        ]
                        model_messages = to_model_messages(full_session)
                        run._graph_run.state.message_history[:] = model_messages[:-1] if model_messages else []

                    history: list[ModelMessage] = run._graph_run.state.message_history

                    # DEBUG: 打印 handle 前后的消息结构
                    if not _first_llm_call:
                        _debug_parts: list[str] = []
                        for _di, _dm in enumerate(history):
                            _dtype: str = "Req" if isinstance(_dm, ModelRequest) else "Resp"
                            _dparts: list[str] = []
                            for _dp in _dm.parts:
                                _dparts.append(type(_dp).__name__)
                            _debug_parts.append(f"  [{_di}] {_dtype}: {_dparts}")
                        log_info(
                            f"[DEBUG_HISTORY] iteration={iteration}, "
                            f"before handle ({len(history)} msgs):\n"
                            + "\n".join(_debug_parts)
                        )

                    # 同步场景允许的 skill 列表到 pre_call_service
                    pre_call_service.allowed_skills = deps.allowed_skills

                    pre_result = await pre_call_service.handle(history, deps=deps)

                    if pre_result.compacted:
                        log_info(f"[COMPACT] iteration={iteration}")
                        agent_working = from_model_messages(pre_result.working_messages)
                        await memory_service.update(
                            task.user_id, task.session_id, agent_working,
                        )
                        deps.file_state_tracker.clear()

                    if _base_len == 0:
                        _base_len = len(pre_result.model_messages)

                    run._graph_run.state.message_history[:] = pre_result.model_messages

                    # 注入 tail reminders（dynamic-context / invoked-skills）到最后一条
                    # user message 的 parts。append → LLM call → strip 成对出现，确保
                    # 同轮内多次 LLM 调用 context 热切换不会叠加，持久化时也干净。
                    from agent_sdk._agent.message.context_injector import (
                        build_dynamic_context_part,
                        build_invoked_skills_part,
                        strip_tail_reminders,
                    )
                    if pre_result.dynamic_text:
                        node.request.parts.append(
                            build_dynamic_context_part(pre_result.dynamic_text)
                        )
                    if pre_result.invoked_skills_tail:
                        node.request.parts.append(
                            build_invoked_skills_part(pre_result.invoked_skills_tail)
                        )

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

                    try:
                        await _emit_model_stream(
                            node, run.ctx, emitter, task,
                            agent_name=agent_name,
                            parent_tool_call_id=ctx.parent_tool_call_id,
                        )
                        _first_llm_call = False
                        node = await run.next(node)
                    finally:
                        # LLM call 完成/异常 → 清掉刚 append 的 tail reminders，让
                        # 下轮 handle() 和持久化都看到干净的 history
                        strip_tail_reminders(run._graph_run.state.message_history)

                elif isinstance(node, CallToolsNode):
                    await _emit_tool_events(node, run.ctx, emitter, task, agent_name=agent_name, parent_tool_call_id=ctx.parent_tool_call_id)
                    node = await run.next(node)

                else:
                    node = await run.next(node)

                iteration += 1
                if iteration >= max_iterations:
                    result.finish_reason = "max_iterations"
                    break

        # Token usage 统计
        usage = run.usage()
        result.usage = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
        }

        # 持久化：确保客户端收到 CHAT_REQUEST_END 时数据已落盘
        if run.result is not None:
            result.final_response = run.result.output
            new_messages: list[ModelMessage] = run.result.all_messages()
            appended = new_messages[_base_len:]
            new_agent_messages = from_model_messages(appended)
            _tag_request_phase(new_agent_messages, task.request_id)
            await transcript_service.append(task.user_id, _transcript_sid, new_agent_messages)
            result.transcript_persisted = True
            if not is_sub_agent:
                await memory_service.insert_batch(task.user_id, task.session_id, new_agent_messages)

    except AgentLoopError as exc:
        # 业务工具主动 raise 的"应当结束本轮"信号（如 WorkflowUnavailableError）。
        # 走有标识的日志，前端收到 ERROR + CHAT_REQUEST_END 后正常关流。
        result.finish_reason = "error"
        exc_type: str = type(exc).__name__
        log_error(
            f"[{exc_type}] agent loop 主动终止 (agent={agent_name}): {exc}",
            exc=exc,
        )
        log_request_end(
            session_id=task.session_id,
            success=False,
            error=f"{exc_type}: {exc}",
            request_id=task.request_id,
        )
        await emitter.emit(EventModel(
            session_id=task.session_id,
            request_id=task.request_id,
            type=EventType.ERROR,
            data={
                # error / message 都塞，前端不同消费方读哪个都能拿到
                "error": str(exc),
                "message": str(exc),
                "error_type": exc_type,
                "fatal": True,
            },
            agent_name=agent_name,
        ))
        # 不再向上 raise——业务可预期的终止，避免 HTTP 500
    except Exception as exc:
        result.finish_reason = "error"
        log_error(f"Agent loop 异常 (agent={agent_name}): {exc}", exc=exc)
        log_request_end(
            session_id=task.session_id,
            success=False,
            error=str(exc),
            request_id=task.request_id,
        )
        await emitter.emit(EventModel(
            session_id=task.session_id,
            request_id=task.request_id,
            type=EventType.ERROR,
            data={"error": str(exc), "message": str(exc)},
            agent_name=agent_name,
        ))
        raise
    else:
        log_request_end(
            session_id=task.session_id,
            success=result.finish_reason == "completed",
            request_id=task.request_id,
            response=result.final_response,
        )
    finally:
        if not is_sub_agent:
            clear_request_context()
            end_data: dict[str, Any] = {"user_id": task.user_id}
            if result.usage is not None:
                end_data["usage"] = result.usage
            await emitter.emit(EventModel(
                session_id=task.session_id,
                request_id=task.request_id,
                type=EventType.CHAT_REQUEST_END,
                data=end_data,
                finish_reason=result.finish_reason,
                agent_name=agent_name,
            ))
            await emitter.close()

    return result

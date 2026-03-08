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
from src.agent.toolset import get_tools
from src.common.session_request_task import SessionRequestTask
from src.config.settings import get_agent_fs_backend, get_backend, get_compact_config
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel
from src.event.event_type import EventType


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
) -> None:
    """流式消费 ModelRequestNode，逐 token 发出 TEXT / TOOL_CALL 事件。

    stream 结束后 node._result 已设置，后续 run.next(node) 不会重复调 LLM。
    """
    async with node.stream(ctx) as agent_stream:
        async for event in agent_stream:
            if isinstance(event, PartStartEvent):
                part = event.part
                if isinstance(part, TextPart) and part.content:
                    await emitter.emit(EventModel(
                        conversation_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TEXT,
                        data={"content": part.content},
                    ))
                elif isinstance(part, ToolCallPart):
                    await emitter.emit(EventModel(
                        conversation_id=task.session_id,
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
                    await emitter.emit(EventModel(
                        conversation_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TEXT,
                        data={"content": delta.content_delta},
                    ))
                elif isinstance(delta, ToolCallPartDelta):  # pragma: no cover — 真实 LLM 流式 tool call 才触发
                    await emitter.emit(EventModel(
                        conversation_id=task.session_id,
                        request_id=task.request_id,
                        type=EventType.TOOL_CALL_ARGS,
                        data={"args_chunk": delta.args_delta},
                    ))


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
                pass
            elif isinstance(event, FunctionToolResultEvent):
                content = event.result.content if hasattr(event.result, "content") else str(event.result)
                await emitter.emit(EventModel(
                    conversation_id=task.session_id,
                    request_id=task.request_id,
                    type=EventType.TOOL_RESULT,
                    data={
                        "tool_name": event.result.tool_name,
                        "tool_call_id": getattr(event.result, "tool_call_id", ""),
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
    backend = get_backend()
    agent_fs_backend = get_agent_fs_backend()

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

    pre_call_service = PreModelCallMessageService(
        compactor=compactor,
        context_messages=context_messages,
        attachment_collector=attachment_collector,
        skill_registry=skill_registry if skill_registry.has_skills() else None,
        invoked_skill_store=invoked_store if skill_registry.has_skills() else None,
    )

    if message_history is None:
        message_history = await memory_service.load(task.user_id, task.session_id)

    try:
        iteration: int = 0

        async with agent.iter(
            task.message,
            deps=deps,
            message_history=message_history,
        ) as run:
            node = run.next_node

            while not isinstance(node, End):
                if task.cancelled:
                    break

                if isinstance(node, ModelRequestNode):
                    history: list[ModelMessage] = run._graph_run.state.message_history

                    # 每轮 LLM 前：context injection + attachment + compact
                    pre_result = await pre_call_service.handle(history)

                    # 若 compact 发生，更新工作集并清除文件状态追踪
                    if pre_result.compacted:
                        await memory_service.update(
                            task.user_id, task.session_id, pre_result.working_messages,
                        )
                        deps.file_state_tracker.clear()

                    # 注入处理后的消息到 run 内部状态
                    run._graph_run.state.message_history[:] = pre_result.model_messages

                    # 流式处理 LLM 响应 → emitter.emit(text / tool_call 事件)
                    await _emit_model_stream(node, run.ctx, emitter, task)

                elif isinstance(node, CallToolsNode):
                    # 工具执行 → emitter.emit(tool_result 事件)
                    await _emit_tool_events(node, run.ctx, emitter, task)

                node = await run.next(node)

                iteration += 1
                if iteration >= max_iterations:
                    break

        # 发送结束事件
        await emitter.emit(EventModel(
            conversation_id=task.session_id,
            request_id=task.request_id,
            type=EventType.CHAT_REQUEST_END,
            data={},
        ))

        # 持久化新消息（过滤 is_meta，分别写 messages.jsonl 和 transcript.jsonl）
        if run.result is not None:
            new_messages: list[ModelMessage] = run.result.all_messages()
            history_len: int = len(message_history) if message_history else 0
            appended = new_messages[history_len:]
            await transcript_service.append(task.user_id, task.session_id, appended)
            await memory_service.insert_batch(task.user_id, task.session_id, appended)

    except Exception as exc:
        # 发送错误事件通知客户端
        await emitter.emit(EventModel(
            conversation_id=task.session_id,
            request_id=task.request_id,
            type=EventType.ERROR,
            data={"message": str(exc)},
        ))
        raise
    finally:
        await emitter.close()

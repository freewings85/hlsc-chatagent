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

from src.agent.compact.compactor import CompactResult, Compactor
from src.agent.deps import AgentDeps
from src.agent.message.context_injector import inject_context
from src.agent.message.history_message_loader import HistoryMessageLoader
from src.agent.prompt.prompt_builder import PromptBuilder
from src.agent.toolset import get_tools
from src.common.session_request_task import SessionRequestTask
from src.config.settings import get_backend, get_compact_config
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
                elif isinstance(delta, ToolCallPartDelta):
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
                await emitter.emit(EventModel(
                    conversation_id=task.session_id,
                    request_id=task.request_id,
                    type=EventType.TOOL_CALL_START,
                    data={
                        "tool_name": event.part.tool_name,
                        "tool_call_id": event.part.tool_call_id or "",
                    },
                ))
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

    Producer 职责：
    - 驱动节点流转（ModelRequestNode → CallToolsNode → ...）
    - 通过 emitter.emit() 发出事件，不关心谁在消费
    - 子函数拿到 emitter 即可发事件，无需层层传递 generator

    消息操作方式：
    - 通过 run._graph_run.state.message_history 直接操作内部消息列表
    - compact / attachment / context 在 ModelRequestNode 前手动修改消息
    - 该列表与 run.all_messages() 是同一引用

    流式事件：
    - ModelRequestNode: 通过 node.stream(ctx) 逐 token 发出 TEXT / TOOL_CALL 事件
    - CallToolsNode: 通过 node.stream(ctx) 发出 TOOL_RESULT 事件
    - stream 完成后 run.next(node) 不会重复执行（内部检查 _result/_next_node）
    """
    try:
        iteration: int = 0

        # 1. PromptBuilder — 加载系统提示词 + 上下文消息
        backend = get_backend()
        prompt_builder: PromptBuilder = PromptBuilder(backend)
        context_messages: list[ModelRequest] = await prompt_builder.build_context_messages(
            user_id=task.user_id,
        )

        # 2. HistoryMessageLoader — 加载历史消息
        history_loader: HistoryMessageLoader = HistoryMessageLoader(backend)
        if message_history is None:
            message_history = await history_loader.load(task.user_id, task.session_id)

        # 3. Compactor — 两层递进压缩
        compactor: Compactor = Compactor(
            config=get_compact_config(),
            history_loader=history_loader,
            user_id=task.user_id,
            session_id=task.session_id,
        )

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
                    # 注入上下文（agent.md + memory.md），每轮 ModelRequestNode 前重新注入
                    history: list[ModelMessage] = run._graph_run.state.message_history
                    inject_context(history, context_messages)

                    # 4. Compactor — 两层递进压缩（microcompact + full compact）
                    compact_result: CompactResult = await compactor.check(history)

                    # TODO: 5. AttachmentCollector.inject(history, compact_result)
                    #   — compact 后恢复上下文（最近文件、任务状态等）
                    #   — 每轮动态 attachment（changed_files、diagnostics 等）

                    # 7. 流式处理 LLM 响应 → emitter.emit(text / tool_call 事件)
                    await _emit_model_stream(node, run.ctx, emitter, task)

                elif isinstance(node, CallToolsNode):
                    # 8. 工具执行 → emitter.emit(tool_result 事件)
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

        # 9. 追加新消息到 messages.jsonl（append-only，过滤 is_meta）
        if run.result is not None:
            new_messages: list[ModelMessage] = run.result.all_messages()
            # all_messages() 包含历史 + 本轮新增，取本轮新增部分
            history_len: int = len(message_history) if message_history else 0
            await history_loader.append(
                task.user_id, task.session_id, new_messages[history_len:],
            )

    except Exception:
        # 发送错误事件通知客户端
        # TODO: emitter.emit(EventModel(type=EventType.ERROR, ...))
        raise
    finally:
        await emitter.close()

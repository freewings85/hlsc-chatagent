"""A2A 协议适配层：将现有 Agent 服务暴露为 A2A 端点。

通过实现 A2A SDK 的 AgentExecutor 接口，在 execute() 中运行现有的
agent loop，将内部事件映射为 A2A 协议格式（artifact/status）。

有状态设计：
- agent loop 在 interrupt 时不被 cancel，跨 execute() 调用保持存活
- 通过 context_id 跟踪活跃的 loop，interrupt reply 通过 Temporal resume 传回

挂载方式：
    from agent_sdk._server.a2a_adapter import mount_a2a
    mount_a2a(app)  # 注册 /.well-known/agent.json + /a2a (JSON-RPC)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Part,
    TextPart,
)
from fastapi import FastAPI

from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType

logger = logging.getLogger(__name__)


@dataclass
class _ActiveLoop:
    """跨 execute() 调用保持的 agent loop 状态。"""

    loop_task: asyncio.Task[None]
    internal_queue: asyncio.Queue[EventModel | None]
    interrupt_key: str | None = None


class ChatAgentExecutor(AgentExecutor):
    """将 Agent 包装为 A2A AgentExecutor。

    有状态：interrupt 时保持 agent loop 存活，下次 execute() 恢复。
    通过 context_id 跟踪活跃的 loop。
    """

    def __init__(
        self,
        agent: Any = None,
        temporal_client_getter: Callable[[], Any] | None = None,
        # 向后兼容（将废弃）
        agent_factory: Callable[..., Any] | None = None,
        deps_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._agent = agent
        self._temporal_client_getter = temporal_client_getter
        self._agent_factory = agent_factory
        self._deps_factory = deps_factory
        # context_id → 活跃的 agent loop
        self._active_loops: dict[str, _ActiveLoop] = {}

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        context_id = context.context_id or "a2a-default"

        user_input = context.get_user_input()
        if not user_input:
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text="No input provided."))]
            )
            await updater.failed(message=msg)
            return

        # 检查是否是 interrupt 恢复
        active = self._active_loops.get(context_id)
        if active and not active.loop_task.done():
            # 恢复：发送 reply 给 Temporal，继续消费事件
            await updater.start_work()
            await self._resume_interrupt(active, user_input)
            try:
                await self._forward_events(
                    active.internal_queue, updater, context, active
                )
            except Exception as exc:
                logger.error(f"A2A resume error: {exc}", exc_info=True)
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Agent error: {exc}"))]
                )
                await updater.failed(message=msg)
                self._cleanup_loop(context_id)
            return

        # 清理可能存在的已完成 loop
        self._cleanup_loop(context_id)

        # 新任务：启动 agent loop
        await updater.start_work()
        metadata = context.metadata or {}
        user_id = metadata.get("user_id", "a2a")

        # 从 A2A message metadata 中提取父级信息（由 call_subagent 传入）
        logger.info("A2A metadata: %s", metadata)
        parent_session_id: str = metadata.get("parent_session_id", "")
        parent_request_id: str = metadata.get("parent_request_id", "")
        request_context = metadata.get("request_context")
        otel_carrier: dict[str, str] = metadata.get("_otel_carrier", {})
        if request_context is not None:
            logger.info("A2A request_context: %s", request_context)

        # session_id：和 mainagent 保持一致，便于按 session 检索全链路
        session_id: str = parent_session_id if parent_session_id else context_id

        if parent_session_id:
            logger.info(
                "A2A subagent: session=%s, parent_request=%s",
                session_id, parent_request_id,
            )

        # 从 metadata 中还原 mainagent 的 OTel trace context，
        # 让 subagent 的 span 挂到 mainagent 的 trace 树下
        parent_otel_context: Any = None
        if otel_carrier:
            try:
                from opentelemetry.propagate import extract
                parent_otel_context = extract(otel_carrier)
            except ImportError:
                pass

        internal_queue: asyncio.Queue[EventModel | None] = asyncio.Queue()

        from agent_sdk._config.settings import get_fs_tools_backend
        from agent_sdk._event.event_emitter import EventEmitter

        emitter = EventEmitter(internal_queue)

        temporal_client = None
        if self._temporal_client_getter:
            temporal_client = self._temporal_client_getter()

        # 使用 Agent.run() 统一入口
        agent = self._agent
        if agent is None:
            raise RuntimeError("ChatAgentExecutor: agent not set")

        # A2A 场景：fs_tools_backend 用全局配置（不加 session 隔离）
        fs_tools_backend = get_fs_tools_backend()

        loop_task = asyncio.create_task(
            agent.run(
                message=user_input,
                user_id=user_id,
                session_id=session_id,
                emitter=emitter,
                temporal_client=temporal_client,
                fs_tools_backend=fs_tools_backend,
                request_context=request_context,
                is_sub_agent=True,
                parent_request_id=parent_request_id or None,
                parent_otel_context=parent_otel_context,
            ),
            name=f"a2a-agent-{context.task_id}",
        )

        def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
            internal_queue.put_nowait(None)

        loop_task.add_done_callback(_ensure_sentinel)

        active = _ActiveLoop(
            loop_task=loop_task, internal_queue=internal_queue
        )
        self._active_loops[context_id] = active

        try:
            await self._forward_events(
                internal_queue, updater, context, active
            )
        except Exception as exc:
            logger.error(f"A2A execute error: {exc}", exc_info=True)
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text=f"Agent error: {exc}"))]
            )
            await updater.failed(message=msg)
            self._cleanup_loop(context_id)

    async def _resume_interrupt(
        self, active: _ActiveLoop, user_reply: str
    ) -> None:
        """恢复中断的 agent loop（Temporal 或内存模式）。"""
        if not active.interrupt_key:
            logger.warning("No interrupt_key to resume")
            return

        temporal_client = None
        if self._temporal_client_getter:
            temporal_client = self._temporal_client_getter()

        from agent_sdk._agent.interrupt import resume

        reply_data = {"reply": user_reply}
        try:
            # client=None 时走内存模式
            await resume(temporal_client, active.interrupt_key, reply_data)
            active.interrupt_key = None  # 已消费
        except Exception as exc:
            logger.error(f"Failed to resume interrupt: {exc}", exc_info=True)

    async def _forward_events(
        self,
        internal_queue: asyncio.Queue[EventModel | None],
        updater: TaskUpdater,
        context: RequestContext,
        active: _ActiveLoop,
    ) -> None:
        """从内部事件队列读取事件，转为 A2A 格式。"""
        context_id = context.context_id or "a2a-default"
        text_buffer: list[str] = []
        # 收集 tool_call_args chunks，按 tool_call_id 拼接
        tool_args_buffer: dict[str, str] = {}

        while True:
            event = await internal_queue.get()
            if event is None:
                break

            if event.type == EventType.TEXT:
                content = event.data.get("content", "")
                if content:
                    text_buffer.append(content)

            elif event.type == EventType.INTERRUPT:
                # HITL：记住 interrupt_key，返回 input-required
                interrupt_key = event.data.get("interrupt_key", "")
                active.interrupt_key = interrupt_key

                question = event.data.get("question", "")
                interrupt_data = {
                    k: v for k, v in event.data.items()
                    if k not in ("question",)
                }
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=question))],
                    metadata=interrupt_data if interrupt_data else None,
                )
                await updater.requires_input(message=msg)
                # 不清理 loop，不 cancel — agent loop 继续 await Temporal signal
                return

            elif event.type == EventType.TOOL_CALL_START:
                # 工具调用开始 → DataPart 通知
                tool_name = event.data.get("tool_name", "")
                tool_call_id = event.data.get("tool_call_id", "")
                await updater.add_artifact(
                    parts=[Part(root=DataPart(data={
                        "event_type": "tool_call_start",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                    }))],
                )

            elif event.type == EventType.TOOL_CALL_ARGS:
                # 收集 args chunks，等 TOOL_RESULT 时一起发出
                tcid = event.data.get("tool_call_id", "")
                chunk = event.data.get("args_chunk", "")
                if tcid and chunk:
                    tool_args_buffer[tcid] = tool_args_buffer.get(tcid, "") + chunk

            elif event.type == EventType.TOOL_RESULT:
                # 先发送该 tool 的完整 args（如果有）
                result_tcid = event.data.get("tool_call_id", "")
                buffered_args = tool_args_buffer.pop(result_tcid, "")
                if buffered_args:
                    await updater.add_artifact(
                        parts=[Part(root=DataPart(data={
                            "event_type": "tool_call_args",
                            "tool_call_id": result_tcid,
                            "args": buffered_args,
                        }))],
                    )
                # 工具结果 → DataPart
                await updater.add_artifact(
                    parts=[Part(root=DataPart(data={
                        "event_type": "tool_result",
                        "tool_name": event.data.get("tool_name", ""),
                        "tool_call_id": event.data.get("tool_call_id", ""),
                        "result": event.data.get("result", ""),
                    }))],
                )

            elif event.type == EventType.TOOL_RESULT_DETAIL:
                card_data = event.data.get("data", {})
                detail_type = event.data.get("detail_type", "card")
                await updater.add_artifact(
                    parts=[Part(root=DataPart(data={
                        "event_type": "tool_result_detail",
                        "card_type": detail_type,
                        **card_data,
                    }))],
                )

            elif event.type == EventType.ERROR:
                error_msg = event.data.get("message", "Unknown error")
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=error_msg))]
                )
                await updater.failed(message=msg)
                self._cleanup_loop(context_id)
                return

            elif event.type == EventType.CHAT_REQUEST_END:
                break

        # 正常完成
        final_text = "".join(text_buffer) if text_buffer else "Done."
        msg = updater.new_agent_message(
            parts=[Part(root=TextPart(text=final_text))]
        )
        await updater.complete(message=msg)
        self._cleanup_loop(context_id)

    def _cleanup_loop(self, context_id: str) -> None:
        """清理已完成或不再需要的 loop。"""
        active = self._active_loops.pop(context_id, None)
        if active and not active.loop_task.done():
            active.loop_task.cancel()

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        context_id = context.context_id or "a2a-default"
        self._cleanup_loop(context_id)
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        msg = updater.new_agent_message(
            parts=[Part(root=TextPart(text="Task cancelled."))]
        )
        await updater.cancel(message=msg)


def _build_agent_card(
    base_url: str = "http://localhost:8100",
    name: str = "ChatAgent",
    description: str = "通用对话 Agent，支持工具调用、文件操作、中断确认等",
    skills: list[AgentSkill] | None = None,
) -> AgentCard:
    """构建 AgentCard 描述当前 agent 的能力。"""
    if skills is None:
        skills = [
            AgentSkill(
                id="chat",
                name="Chat",
                description="General-purpose chat with tool use, file operations, and HITL support",
                tags=["chat", "tools", "hitl"],
            ),
        ]
    return AgentCard(
        name=name,
        description=description,
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=skills,
    )


def mount_a2a(
    app: FastAPI,
    *,
    agent: Any = None,
    base_url: str = "http://localhost:8100",
    temporal_client_getter: Callable[[], Any] | None = None,
    agent_card_name: str = "ChatAgent",
    agent_card_description: str = "通用对话 Agent，支持工具调用、文件操作、中断确认等",
    agent_card_skills: list[AgentSkill] | None = None,
    rpc_url: str = "/a2a",
    # 向后兼容（将废弃）
    agent_factory: Callable[..., Any] | None = None,
    deps_factory: Callable[..., Any] | None = None,
) -> None:
    """将 A2A 端点挂载到现有 FastAPI 应用。"""
    agent_card = _build_agent_card(
        base_url,
        name=agent_card_name,
        description=agent_card_description,
        skills=agent_card_skills,
    )
    executor = ChatAgentExecutor(
        agent=agent,
        temporal_client_getter=temporal_client_getter,
    )
    task_store = InMemoryTaskStore()

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    a2a_app = A2AFastAPIApplication(
        agent_card=agent_card,
        http_handler=handler,
    )
    a2a_app.add_routes_to_app(app, rpc_url=rpc_url)

    logger.info(f"A2A endpoints mounted: /.well-known/agent.json, POST {rpc_url}")

"""A2A 协议适配层：将现有 Agent 服务暴露为 A2A 端点。

通过实现 A2A SDK 的 AgentExecutor 接口，在 execute() 中运行现有的
agent loop，将内部事件映射为 A2A 协议格式（artifact/status）。

挂载方式：
    from src.server.a2a_adapter import mount_a2a
    mount_a2a(app)  # 注册 /.well-known/agent.json + /a2a (JSON-RPC)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

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

from src.agent.deps import AgentDeps
from src.agent.loop import create_agent, run_main_agent
from src.agent.model import create_model
from src.agent.tools import ALL_FS_TOOLS, create_default_tool_map
from src.common.session_request_task import SessionRequestTask
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel
from src.event.event_type import EventType

logger = logging.getLogger(__name__)


class ChatAgentExecutor(AgentExecutor):
    """将现有 agent loop 包装为 A2A AgentExecutor。

    每次 execute() 调用：
    1. 创建内部 EventEmitter（asyncio.Queue）
    2. 启动 agent loop 后台任务
    3. 消费内部事件，映射为 A2A 事件推入 A2A EventQueue
    """

    def __init__(self, temporal_client_getter: Any = None) -> None:
        self._temporal_client_getter = temporal_client_getter

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        user_input = context.get_user_input()
        if not user_input:
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text="No input provided."))]
            )
            await updater.failed(message=msg)
            return

        # 使用 context_id 作为 session_id（同一对话多次交互共享）
        session_id = context.context_id or "a2a-default"
        user_id = "a2a"

        # 从 A2A metadata 中提取可选配置
        metadata = context.metadata
        if metadata.get("user_id"):
            user_id = metadata["user_id"]

        # 创建内部事件管道
        internal_queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(internal_queue)

        # 获取 Temporal client
        temporal_client = None
        if self._temporal_client_getter:
            temporal_client = self._temporal_client_getter()

        # 创建 agent 和 deps
        model = create_model()
        agent = create_agent(model)
        deps = AgentDeps(
            session_id=session_id,
            user_id=user_id,
            available_tools=list(ALL_FS_TOOLS),
            tool_map=create_default_tool_map(),
            temporal_client=temporal_client,
        )

        task = SessionRequestTask(
            session_id=session_id,
            message=user_input,
            user_id=user_id,
            sinker=None,  # type: ignore[arg-type]
        )

        # 后台启动 agent loop
        loop_task = asyncio.create_task(
            run_main_agent(emitter, task, agent, deps),
            name=f"a2a-agent-{context.task_id}",
        )

        def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
            internal_queue.put_nowait(None)

        loop_task.add_done_callback(_ensure_sentinel)

        # 消费内部事件 → 映射为 A2A 事件
        try:
            await self._forward_events(
                internal_queue, updater, event_queue, context
            )
        except Exception as exc:
            logger.error(f"A2A execute error: {exc}", exc_info=True)
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text=f"Agent error: {exc}"))]
            )
            await updater.failed(message=msg)
        finally:
            if not loop_task.done():
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _forward_events(
        self,
        internal_queue: asyncio.Queue[EventModel | None],
        updater: TaskUpdater,
        event_queue: EventQueue,
        context: RequestContext,
    ) -> None:
        """从内部事件队列读取事件，转为 A2A 格式。"""
        text_buffer: list[str] = []

        while True:
            event = await internal_queue.get()
            if event is None:
                break

            if event.type == EventType.TEXT:
                content = event.data.get("content", "")
                if content:
                    text_buffer.append(content)
                    # 逐块发送文本 artifact
                    msg = updater.new_agent_message(
                        parts=[Part(root=TextPart(text=content))]
                    )
                    await updater.add_artifact(
                        parts=[Part(root=TextPart(text=content))],
                        append=True,
                    )

            elif event.type == EventType.INTERRUPT:
                # HITL：发送 input-required 状态
                question = event.data.get("question", "")
                interrupt_data = {
                    k: v
                    for k, v in event.data.items()
                    if k not in ("question",)
                }
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=question))],
                    metadata=interrupt_data if interrupt_data else None,
                )
                await updater.requires_input(message=msg)
                return  # execute() 结束，等 client 下次 sendSubscribe

            elif event.type == EventType.TOOL_RESULT_DETAIL:
                # 卡片数据 → DataPart artifact
                card_data = event.data.get("data", {})
                detail_type = event.data.get("detail_type", "card")
                await updater.add_artifact(
                    parts=[
                        Part(
                            root=DataPart(
                                data={
                                    "card_type": detail_type,
                                    **card_data,
                                }
                            )
                        )
                    ],
                )

            elif event.type == EventType.TOOL_CALL_START:
                # 工具调用开始 — 可选：通知 client agent 在执行工具
                pass

            elif event.type == EventType.TOOL_RESULT:
                # 工具结果 — 不直接暴露给 A2A client（agent 内部消费）
                pass

            elif event.type == EventType.ERROR:
                error_msg = event.data.get("message", "Unknown error")
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=error_msg))]
                )
                await updater.failed(message=msg)
                return

            elif event.type == EventType.CHAT_REQUEST_END:
                # 对话结束 → completed
                break

        # 正常完成
        final_text = "".join(text_buffer) if text_buffer else "Done."
        msg = updater.new_agent_message(
            parts=[Part(root=TextPart(text=final_text))]
        )
        await updater.complete(message=msg)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        msg = updater.new_agent_message(
            parts=[Part(root=TextPart(text="Task cancelled."))]
        )
        await updater.cancel(message=msg)


def _build_agent_card(base_url: str = "http://localhost:8100") -> AgentCard:
    """构建 AgentCard 描述当前 agent 的能力。"""
    return AgentCard(
        name="ChatAgent",
        description="通用对话 Agent，支持工具调用、文件操作、中断确认等",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="chat",
                name="Chat",
                description="General-purpose chat with tool use, file operations, and HITL support",
                tags=["chat", "tools", "hitl"],
            ),
        ],
    )


def mount_a2a(
    app: FastAPI,
    *,
    base_url: str = "http://localhost:8100",
    temporal_client_getter: Any = None,
) -> None:
    """将 A2A 端点挂载到现有 FastAPI 应用。

    挂载后新增：
    - GET  /.well-known/agent.json — AgentCard 发现
    - POST /a2a                    — A2A JSON-RPC 端点（send/sendSubscribe）

    Args:
        app: 现有 FastAPI 应用
        base_url: Agent 的公开 URL（用于 AgentCard）
        temporal_client_getter: 可选的获取 Temporal client 的回调
    """
    agent_card = _build_agent_card(base_url)
    executor = ChatAgentExecutor(temporal_client_getter=temporal_client_getter)
    task_store = InMemoryTaskStore()

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    a2a_app = A2AFastAPIApplication(
        agent_card=agent_card,
        http_handler=handler,
    )
    a2a_app.add_routes_to_app(app, rpc_url="/a2a")

    logger.info("A2A endpoints mounted: /.well-known/agent.json, POST /a2a")

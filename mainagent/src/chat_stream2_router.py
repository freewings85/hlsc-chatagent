"""/chat/stream2 路由：按 agent_type 路由到预构建的 Agent 实例。

请求体与 SDK 的 /chat/stream 完全一致，仅多一个**必填**字段 `agent_type`：

    {
      "user_id": "...",
      "session_id": "...",
      "message": "你好",
      "agent_type": "searchshops_collect",   // 必填
      "context": { ... }                       // 可选，同 /chat/stream
    }

Agent 实例 map 由 app.py 启动时按 agents.yaml 预构建一次，注入进来；请求到达时只做
"按 agent_type 查 map"的 O(1) 查找，未命中即 400。

SSE 协议沿用 SDK /chat/stream：EventEmitter → EventModel → queue → SSE，事件类型
（chat_request_start / text / tool_call_* / chat_request_end / error）和 data 结构
完全不动。commit_policy 通过 agent.run() 的 commit_filter 参数按 AgentSpec 生效。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent_sdk import Agent
from agent_sdk._agent.agent_message import AgentMessage, AssistantMessage, UserMessage
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType

from src.agent_registry import AGENT_REGISTRY, AgentSpec, CommitPolicy

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter()

# 由 app.py 启动时注入：agent_type → 预构建 Agent 实例
_agent_instances: dict[str, Agent] = {}

# per-session 锁，和 SDK /chat/stream 同款（防并发）
_session_locks: dict[str, asyncio.Lock] = {}


def set_agent_instances(instances: dict[str, Agent]) -> None:
    """由 app.py 启动时调，填充预构建的 agent 实例 map。"""
    global _agent_instances
    _agent_instances = instances


def _build_commit_filter(
    policy: CommitPolicy, agent_type: str
) -> Any:
    """按 commit_policy 返回传给 agent.run(commit_filter=...) 的过滤函数。

    - full：去掉首位 UserMessage（本轮 user_prompt 已由外部管理），其余全写
    - text_only：只留 AssistantMessage 且 content 非空；tool_calls 清空，不持久化 tool 链
    - nothing：返回 []，触发 SDK 跳过 insert_batch
    """

    def _filter(msgs: list[AgentMessage]) -> list[AgentMessage]:
        if policy == "nothing":
            return []
        trimmed: list[AgentMessage] = list(msgs)
        if trimmed and isinstance(trimmed[0], UserMessage):
            trimmed = trimmed[1:]
        if policy == "full":
            for m in trimmed:
                m.metadata.setdefault("agent", agent_type)
            return trimmed
        # text_only
        result: list[AgentMessage] = []
        for m in trimmed:
            if isinstance(m, AssistantMessage) and m.content.strip():
                result.append(
                    AssistantMessage(
                        content=m.content,
                        tool_calls=[],
                        metadata={**m.metadata, "agent": agent_type},
                        timestamp=m.timestamp,
                    )
                )
        return result

    return _filter


def _resolve_trace_context(raw_request: Any) -> tuple[str, object | None]:
    """从请求 header 提取 OTel trace context（和 SDK /chat/stream 同款）。"""
    try:
        from opentelemetry.propagate import extract
        from opentelemetry.trace import INVALID_TRACE_ID, format_trace_id, get_current_span

        ctx = extract(dict(raw_request.headers))
        trace_id: int = get_current_span(ctx).get_span_context().trace_id
        if trace_id != INVALID_TRACE_ID:
            return format_trace_id(trace_id), ctx
    except Exception:
        pass
    return uuid.uuid4().hex, None


@router.post("/chat/stream2")
async def chat_stream2(request: dict[str, Any], raw_request: Request) -> Any:
    # 1) agent_type 必填校验
    agent_type_raw: object = request.get("agent_type")
    if not isinstance(agent_type_raw, str) or agent_type_raw == "":
        raise HTTPException(status_code=400, detail="agent_type is required")
    agent_type: str = agent_type_raw

    agent: Agent | None = _agent_instances.get(agent_type)
    spec: AgentSpec | None = AGENT_REGISTRY.get(agent_type)
    if agent is None or spec is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown agent_type={agent_type!r}",
        )

    # 2) 其他字段沿用 /chat/stream 约定
    session_id: str = str(request.get("session_id", "default"))
    user_id: str = str(request.get("user_id", "anonymous"))
    message: str = str(request.get("message", ""))
    context: Any = request.get("context")

    # request_id 优先用 body 里的（orchestrator → workflow 全链路同 id）；
    # body 没传才 fallback 到 OTel trace_id 或 uuid
    trace_request_id, parent_otel_context = _resolve_trace_context(raw_request)
    body_request_id: str = str(request.get("request_id", "") or "")
    request_id: str = body_request_id or trace_request_id

    # 3) per-session 锁
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    session_lock: asyncio.Lock = _session_locks[session_id]

    if session_lock.locked():
        return JSONResponse(
            status_code=429,
            content={"error": "该会话有请求正在处理中，请稍后重试", "session_id": session_id},
        )

    # 4) 组 emitter + queue
    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter: EventEmitter = EventEmitter(queue)

    # 5) 按 spec 配历史 & commit filter
    #    load_history=False → 传 [] 阻止 SDK 自动从 memory 加载
    #    load_history=True  → 传 None 让 SDK 正常加载
    message_history: list[Any] | None = None if spec.load_history else []
    commit_filter = _build_commit_filter(spec.commit_policy, agent_type)

    async def _locked_run() -> None:
        async with session_lock:
            try:
                await agent.run(
                    message,
                    user_id=user_id,
                    session_id=session_id,
                    emitter=emitter,
                    request_context=context,
                    request_id=request_id,
                    parent_otel_context=parent_otel_context,
                    message_history=message_history,
                    commit_filter=commit_filter,
                )
            finally:
                if session_id in _session_locks and not session_lock.locked():
                    _session_locks.pop(session_id, None)

    loop_task: asyncio.Task[None] = asyncio.create_task(
        _locked_run(),
        name=f"agent-stream2-{session_id}-{agent_type}",
    )
    task_id: str = f"stream2-{session_id}-{id(loop_task)}"

    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    async def generate():  # type: ignore[no-untyped-def]
        try:
            start_event: EventModel = EventModel(
                session_id=session_id,
                request_id="",
                type=EventType.CHAT_REQUEST_START,
                data={"task_id": task_id},
            )
            yield f"event: {start_event.type.value}\ndata: {start_event.to_json()}\n\n"
            while True:
                event: EventModel | None = await queue.get()
                if event is None:
                    break
                yield f"event: {event.type.value}\ndata: {event.to_json()}\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            if not loop_task.done():
                loop_task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

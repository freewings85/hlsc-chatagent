"""call_subagent：封装 A2A 协议通信、事件转发、interrupt 中继。

两种用法：

1. 一行调用（简单场景）：
   result = await call_subagent(ctx, url=..., message=...)

2. 展开模式（需要介入 A2A 过程）：
   async with call_subagent(ctx, url=..., message=...) as session:
       async for event in session:
           # 可选：介入 event
       result = session.result
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.interrupt import interrupt as _do_interrupt
from agent_sdk._config.settings import get_temporal_config
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType

logger = logging.getLogger(__name__)

# agent card 缓存：url → agent_name
_agent_card_cache: dict[str, str] = {}


@dataclass
class SubagentEvent:
    """A2A 过程中的一个状态变更。"""

    state: str  # "completed" | "failed" | "input-required" | "working"
    task_id: str
    question: str | None = None  # input-required 时的问题文本（可修改）
    result_text: str | None = None  # completed 时的结果文本
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class SubagentSession:
    """A2A 会话，支持 async for 迭代事件。

    迭代器内部自动执行默认行为（事件转发、interrupt 中继）。
    yield 出的 event 给开发者一个"观察和介入"的机会。
    不写任何处理代码也是正确的。
    """

    def __init__(
        self,
        ctx: RunContext[AgentDeps],
        url: str,
        message: str,
        timeout: float,
        agent_name: str,
    ) -> None:
        self._ctx = ctx
        self._url = url
        self._message = message
        self._timeout = timeout
        self.agent_name: str = agent_name
        self.result: str = ""

        # 内部状态
        self._agent_path: str = ""
        self._parent_tool_call_id: str = ""
        self._emitted_artifact_ids: set[str] = set()
        self._text_parts: list[str] = []

    async def _init(self) -> None:
        """初始化 agent_path 等上下文信息。"""
        parent_agent_path = getattr(self._ctx, "agent_path", "main")
        if not parent_agent_path:
            parent_agent_path = "main"
        self._agent_path = f"{parent_agent_path}|{self.agent_name}"
        self._parent_tool_call_id = getattr(self._ctx, "tool_call_id", None) or ""

    def __aiter__(self) -> AsyncIterator[SubagentEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[SubagentEvent]:
        """核心迭代器：驱动 A2A 通信并 yield 每个状态变更。"""
        ctx = self._ctx
        session_id = ctx.deps.session_id

        context_id = f"sa-{session_id}-{uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
            # 首次 A2A 调用
            result = await _a2a_send(client, self._url, context_id, self._message)

            while True:
                task_state = result.get("status", {}).get("state", "")
                task_id = result.get("id", "")

                # 发送 artifacts 事件给前端（默认行为）
                await self._emit_artifacts(result)

                event = SubagentEvent(
                    state=task_state,
                    task_id=task_id,
                    raw=result,
                    artifacts=result.get("artifacts", []),
                )

                if task_state == "completed":
                    status_msg = result.get("status", {}).get("message")
                    completed_text = _extract_text(status_msg) if status_msg else ""
                    event.result_text = completed_text
                    if completed_text and completed_text not in self._text_parts:
                        self._text_parts.append(completed_text)
                        await self._emit_text(completed_text)

                    yield event

                    self.result = "".join(self._text_parts) if self._text_parts else "Subagent 执行完成"
                    return

                elif task_state == "failed":
                    error = _extract_text(result.get("status", {}).get("message"))
                    event.result_text = error
                    yield event
                    self.result = f"{self.agent_name} 失败: {error}"
                    return

                elif task_state == "input-required":
                    status_msg = result.get("status", {}).get("message", {})
                    question = _extract_text(status_msg)
                    event.question = question

                    # yield 给开发者，开发者可修改 event.question
                    yield event

                    # 默认行为：interrupt 中继
                    user_reply = await self._relay_interrupt(event.question or question)

                    # 用 reply 继续 A2A
                    result = await _a2a_send(
                        client, self._url, context_id, user_reply, task_id=task_id,
                    )

                else:
                    # working 等其他状态
                    yield event
                    break

    async def _emit_artifacts(self, task_result: dict[str, Any]) -> None:
        """从 A2A response 中提取 artifacts，转为 EventModel 发给前端。"""
        emitter = self._ctx.deps.emitter
        if emitter is None:
            return

        session_id = self._ctx.deps.session_id
        artifacts = task_result.get("artifacts", [])

        for artifact in artifacts:
            art_id = artifact.get("artifactId", "") or artifact.get("index", "")
            if art_id:
                if art_id in self._emitted_artifact_ids:
                    continue
                self._emitted_artifact_ids.add(art_id)

            parts = artifact.get("parts", [])
            for part in parts:
                kind = part.get("kind", "") or part.get("type", "")
                if kind == "text":
                    text = part.get("text", "")
                    if text:
                        self._text_parts.append(text)
                        await emitter.emit(EventModel(
                            session_id=session_id,
                            request_id="",
                            type=EventType.TEXT,
                            data={"content": text},
                            agent_path=self._agent_path,
                            parent_tool_call_id=self._parent_tool_call_id,
                        ))
                elif kind == "data":
                    data = part.get("data", {})
                    event_type = data.get("event_type", "")
                    await self._emit_data_artifact(event_type, data)

    async def _emit_data_artifact(
        self, event_type: str, data: dict[str, Any]
    ) -> None:
        """将 data artifact 转为对应 EventModel。"""
        emitter = self._ctx.deps.emitter
        if emitter is None:
            return

        session_id = self._ctx.deps.session_id
        type_map: dict[str, EventType] = {
            "tool_call_start": EventType.TOOL_CALL_START,
            "tool_result": EventType.TOOL_RESULT,
            "tool_result_detail": EventType.TOOL_RESULT_DETAIL,
        }
        etype = type_map.get(event_type)
        if etype is None:
            return

        await emitter.emit(EventModel(
            session_id=session_id,
            request_id="",
            type=etype,
            data=data,
            agent_path=self._agent_path,
            parent_tool_call_id=self._parent_tool_call_id,
        ))

    async def _emit_text(self, text: str) -> None:
        """发送 TEXT 事件给前端。"""
        emitter = self._ctx.deps.emitter
        if emitter is None:
            return
        await emitter.emit(EventModel(
            session_id=self._ctx.deps.session_id,
            request_id="",
            type=EventType.TEXT,
            data={"content": text},
            agent_path=self._agent_path,
            parent_tool_call_id=self._parent_tool_call_id,
        ))

    async def _relay_interrupt(self, question: str) -> str:
        """中继 interrupt：subagent input-required → mainagent interrupt → 用户回复。"""
        ctx = self._ctx
        session_id = ctx.deps.session_id
        temporal_client = ctx.deps.temporal_client
        emitter = ctx.deps.emitter

        main_interrupt_key = f"interrupt-{session_id}-{uuid4().hex[:8]}"

        async def _emit_interrupt(callback_data: dict[str, Any], interrupt_id: str) -> None:
            if emitter is not None:
                await emitter.emit(EventModel(
                    session_id=session_id,
                    request_id="",
                    type=EventType.INTERRUPT,
                    data={
                        "type": "confirm",
                        "question": question,
                        "interrupt_id": interrupt_id,
                        "interrupt_key": main_interrupt_key,
                        "source": self.agent_name,
                    },
                    agent_path=self._agent_path,
                    parent_tool_call_id=self._parent_tool_call_id,
                ))

        config = get_temporal_config()
        response = await _do_interrupt(
            temporal_client,
            key=main_interrupt_key,
            callback=_emit_interrupt,
            data={"question": question, "type": "confirm"},
            task_queue=config.interrupt_task_queue,
        )

        return response.get("reply", "")


async def _fetch_agent_name(url: str, timeout: float = 10.0) -> str:
    """从 subagent 的 /.well-known/agent.json 获取 agent name（带缓存）。"""
    if url in _agent_card_cache:
        return _agent_card_cache[url]

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.get(f"{url}/.well-known/agent.json")
            resp.raise_for_status()
            card = resp.json()
            name = card.get("name", "subagent")
            _agent_card_cache[url] = name
            return name
    except Exception as exc:
        logger.warning("Failed to fetch agent card from %s: %s", url, exc)
        # fallback：从 URL 推断
        return "subagent"


async def _a2a_send(
    client: httpx.AsyncClient,
    url: str,
    context_id: str,
    message: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """发送 A2A message/send 请求。"""
    msg: dict[str, Any] = {
        "role": "user",
        "parts": [{"kind": "text", "text": message}],
        "messageId": uuid4().hex,
        "contextId": context_id,
    }
    if task_id:
        msg["taskId"] = task_id

    request_body = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {"message": msg},
    }

    resp = await client.post(f"{url}/a2a", json=request_body)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"A2A error: {data['error']}")

    return data.get("result", {})


def _extract_text(msg: Any) -> str:
    """从 A2A Message 中提取文本内容。"""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        parts = msg.get("parts", [])
        texts = []
        for part in parts:
            kind = part.get("kind", "") or part.get("type", "")
            if kind == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts) if texts else str(msg)
    return str(msg)


@asynccontextmanager
async def call_subagent_session(
    ctx: RunContext[AgentDeps],
    *,
    url: str,
    message: str,
    timeout: float = 300.0,
) -> AsyncIterator[SubagentSession]:
    """展开模式：async with + async for 可介入 A2A 过程。

    用法：
        async with call_subagent_session(ctx, url=..., message=...) as session:
            async for event in session:
                if event.state == "input-required":
                    event.question = f"[前缀] {event.question}"
            return session.result

    async for 循环中不写任何代码也是正确的 —— SDK 的默认行为
    （事件转发、interrupt 中继）在迭代器内部自动执行。

    Args:
        ctx: Pydantic AI RunContext
        url: subagent 的 base URL
        message: 发给 subagent 的消息
        timeout: HTTP 超时（秒）

    Yields:
        SubagentSession 对象，支持 async for 迭代事件
    """
    agent_name = await _fetch_agent_name(url)
    session = SubagentSession(ctx, url, message, timeout, agent_name)
    await session._init()
    yield session


async def call_subagent(
    ctx: RunContext[AgentDeps],
    *,
    url: str,
    message: str,
    timeout: float = 300.0,
) -> str:
    """一行调用 subagent，返回最终结果。

    封装 A2A 协议通信、事件转发、interrupt 中继。
    等价于 async with call_subagent_session() + async for 但不做任何自定义处理。

    Args:
        ctx: Pydantic AI RunContext，提供 deps（emitter, temporal_client 等）
        url: subagent 的 base URL（e.g. "http://localhost:8101"）
        message: 发给 subagent 的消息
        timeout: HTTP 超时（秒）

    Returns:
        subagent 的最终结果字符串
    """
    async with call_subagent_session(ctx, url=url, message=message, timeout=timeout) as session:
        async for _event in session:
            pass  # 默认行为在迭代器内部自动执行
    return session.result

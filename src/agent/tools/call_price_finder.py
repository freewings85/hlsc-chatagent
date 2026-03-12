"""call_price_finder 工具：通过 A2A 协议调用 PriceFinder subagent。

将 subagent 的事件流转为带 agent_path / parent_tool_call_id 的 EventModel
转发给前端，实现 tool 卡片内嵌套展示 subagent 输出。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

import httpx
from pydantic_ai import RunContext

from src.agent.deps import AgentDeps
from src.agent.interrupt import interrupt as _do_interrupt
from src.config.settings import get_temporal_config
from src.event.event_model import EventModel
from src.event.event_type import EventType

logger = logging.getLogger(__name__)

# PriceFinder subagent 地址（可通过环境变量配置）
import os

PRICE_FINDER_URL = os.getenv("PRICE_FINDER_URL", "http://localhost:8101")


async def call_price_finder(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """Call the PriceFinder subagent to find the best price for a car repair project.

    This tool communicates with a remote PriceFinder agent via A2A protocol.
    The subagent may ask the user for confirmation during execution.

    Args:
        query: Description of what to search for (e.g. "更换刹车片").

    Returns:
        The subagent's final response.
    """
    emitter = ctx.deps.emitter
    session_id = ctx.deps.session_id
    temporal_client = ctx.deps.temporal_client

    # 获取当前 tool call 的 ID（由 Pydantic AI 在 CallToolsNode 中设置）
    # 这个 ID 用于 parent_tool_call_id，让前端知道 subagent 事件隶属于哪个 tool
    parent_tool_call_id = getattr(ctx, "tool_call_id", None) or ""
    agent_path = "main|price_finder"

    context_id = f"pf-{session_id}-{uuid4().hex[:8]}"
    final_text_parts: list[str] = []
    _emitted_artifact_ids: set[str] = set()  # 去重：避免 resume 后重复发送 artifacts

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        # 首次调用
        result = await _a2a_send(client, context_id, query)

        while True:
            task_state = result.get("status", {}).get("state", "")
            task_id = result.get("id", "")

            # 处理 artifacts（去重）
            await _emit_artifacts(
                result, emitter, session_id, agent_path,
                parent_tool_call_id, final_text_parts,
                _emitted_artifact_ids,
            )

            if task_state == "completed":
                # 从 status.message 提取最终文本（updater.complete 放在这里）
                status_msg = result.get("status", {}).get("message")
                if status_msg:
                    completed_text = _extract_text(status_msg)
                    if completed_text and completed_text not in final_text_parts:
                        final_text_parts.append(completed_text)
                break
            elif task_state == "failed":
                error = _extract_text(result.get("status", {}).get("message"))
                return f"PriceFinder 失败: {error}"
            elif task_state == "input-required":
                # 从 status.message 中提取 question
                status_msg = result.get("status", {}).get("message", {})
                question = _extract_text(status_msg)
                metadata = status_msg.get("metadata", {}) if isinstance(status_msg, dict) else {}
                interrupt_key = metadata.get("interrupt_key", "")

                # 通过 main agent 的 interrupt 机制转发给前端
                main_interrupt_key = f"interrupt-{session_id}-{uuid4().hex[:8]}"

                async def _emit_interrupt(callback_data: dict, interrupt_id: str) -> None:
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
                                "source": "price_finder",
                            },
                            agent_path=agent_path,
                            parent_tool_call_id=parent_tool_call_id,
                        ))

                config = get_temporal_config()
                response = await _do_interrupt(
                    temporal_client,
                    key=main_interrupt_key,
                    callback=_emit_interrupt,
                    data={"question": question, "type": "confirm"},
                    task_queue=config.interrupt_task_queue,
                )

                user_reply = response.get("reply", "")

                # 同时把 reply 发给远程 subagent（通过 A2A 继续同一个 task）
                # 同时也 resume subagent 的 Temporal interrupt
                # 方式：通过 A2A sendSubscribe 带 reply 继续
                result = await _a2a_send(
                    client, context_id, user_reply, task_id=task_id,
                )
            else:
                # working 或其他状态，不应该在非流式中出现
                break

    return "".join(final_text_parts) if final_text_parts else "PriceFinder 执行完成"


async def _a2a_send(
    client: httpx.AsyncClient,
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

    resp = await client.post(f"{PRICE_FINDER_URL}/a2a", json=request_body)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"A2A error: {data['error']}")

    return data.get("result", {})


async def _emit_artifacts(
    task_result: dict[str, Any],
    emitter: Any,
    session_id: str,
    agent_path: str,
    parent_tool_call_id: str,
    text_parts: list[str],
    emitted_ids: set[str] | None = None,
) -> None:
    """从 A2A task result 中提取 artifacts，转为 EventModel 发给前端。"""
    if emitter is None:
        return

    artifacts = task_result.get("artifacts", [])
    for artifact in artifacts:
        # 用 artifact index（或 id）去重，避免 resume 后重复发送
        art_id = artifact.get("artifactId", "") or artifact.get("index", "")
        if emitted_ids is not None and art_id:
            if art_id in emitted_ids:
                continue
            emitted_ids.add(art_id)
        parts = artifact.get("parts", [])
        for part in parts:
            kind = part.get("kind", "") or part.get("type", "")
            if kind == "text":
                text = part.get("text", "")
                if text:
                    text_parts.append(text)
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id="",
                        type=EventType.TEXT,
                        data={"content": text},
                        agent_path=agent_path,
                        parent_tool_call_id=parent_tool_call_id,
                    ))
            elif kind == "data":
                data = part.get("data", {})
                event_type = data.get("event_type", "")

                if event_type == "tool_call_start":
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id="",
                        type=EventType.TOOL_CALL_START,
                        data={
                            "tool_name": data.get("tool_name", ""),
                            "tool_call_id": data.get("tool_call_id", ""),
                        },
                        agent_path=agent_path,
                        parent_tool_call_id=parent_tool_call_id,
                    ))
                elif event_type == "tool_result":
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id="",
                        type=EventType.TOOL_RESULT,
                        data={
                            "tool_name": data.get("tool_name", ""),
                            "tool_call_id": data.get("tool_call_id", ""),
                            "result": data.get("result", ""),
                        },
                        agent_path=agent_path,
                        parent_tool_call_id=parent_tool_call_id,
                    ))
                elif event_type == "tool_result_detail":
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id="",
                        type=EventType.TOOL_RESULT_DETAIL,
                        data=data,
                        agent_path=agent_path,
                        parent_tool_call_id=parent_tool_call_id,
                    ))


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

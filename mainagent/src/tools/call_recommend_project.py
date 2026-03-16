"""call_recommend_project 工具：通过 A2A 协议调用 RecommendProject subagent。

MainAgent 从 RequestContext 中提取车辆信息，连同用户问题一起
序列化为 JSON 传给 SubAgent，实现结构化参数传递。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.interrupt import interrupt as _do_interrupt
from agent_sdk._config.settings import get_temporal_config
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType

from src.config import RECOMMEND_PROJECT_URL


async def call_recommend_project(
    ctx: RunContext[AgentDeps],
    query: str,
    vin_code: str = "",
    car_model_name: str = "",
    mileage_km: float = 0.0,
    car_age_year: float = 0.0,
) -> str:
    """调用 RecommendProject subagent，根据车辆里程数、车龄、车型推荐养车项目。

    根据车辆的实际状况（里程、车龄、车型），智能推荐需要做的维修保养项目。
    当推荐多个项目时，subagent 会中断返回项目列表让用户选择。

    Args:
        query: 用户的需求描述，如"我的车该做什么保养了"、"推荐养车项目"。
        vin_code: 车辆 VIN 码。
        car_model_name: 车型名称，如"2024款 宝马 325Li"。
        mileage_km: 当前里程数（千米）。
        car_age_year: 车龄（年）。

    Returns:
        推荐的养车项目信息 JSON。
    """
    emitter = ctx.deps.emitter
    session_id: str = ctx.deps.session_id
    temporal_client = ctx.deps.temporal_client

    parent_tool_call_id: str = getattr(ctx, "tool_call_id", None) or ""
    agent_path: str = "main|recommend_project"

    # 构造结构化 payload 传给 SubAgent
    payload: dict[str, Any] = {
        "query": query,
        "vehicle_info": {
            "vin_code": vin_code,
            "car_model_name": car_model_name,
            "mileage_km": mileage_km,
            "car_age_year": car_age_year,
        },
    }
    message_text: str = json.dumps(payload, ensure_ascii=False)

    context_id: str = f"rp-{session_id}-{uuid4().hex[:8]}"
    final_text_parts: list[str] = []
    _emitted_artifact_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        result: dict[str, Any] = await _a2a_send(client, context_id, message_text)

        while True:
            task_state: str = result.get("status", {}).get("state", "")
            task_id: str = result.get("id", "")

            # 处理 artifacts（去重）
            await _emit_artifacts(
                result, emitter, session_id, agent_path,
                parent_tool_call_id, final_text_parts,
                _emitted_artifact_ids,
            )

            if task_state == "completed":
                status_msg: Any = result.get("status", {}).get("message")
                if status_msg:
                    completed_text: str = _extract_text(status_msg)
                    if completed_text and completed_text not in final_text_parts:
                        final_text_parts.append(completed_text)
                        if emitter is not None:
                            await emitter.emit(EventModel(
                                session_id=session_id,
                                request_id="",
                                type=EventType.TEXT,
                                data={"content": completed_text},
                                agent_path=agent_path,
                                parent_tool_call_id=parent_tool_call_id,
                            ))
                break
            elif task_state == "failed":
                error: str = _extract_text(result.get("status", {}).get("message"))
                return f"RecommendProject 失败: {error}"
            elif task_state == "input-required":
                # 从 status.message 中提取 question 和 options
                status_msg = result.get("status", {}).get("message", {})
                question: str = _extract_text(status_msg)
                metadata: dict[str, Any] = (
                    status_msg.get("metadata", {}) if isinstance(status_msg, dict) else {}
                )
                interrupt_key: str = metadata.get("interrupt_key", "")

                # 通过 MainAgent 的 interrupt 机制转发给前端
                main_interrupt_key: str = f"interrupt-{session_id}-{uuid4().hex[:8]}"

                async def _emit_interrupt(callback_data: dict[str, Any], interrupt_id: str) -> None:
                    if emitter is not None:
                        await emitter.emit(EventModel(
                            session_id=session_id,
                            request_id="",
                            type=EventType.INTERRUPT,
                            data={
                                "type": "select",
                                "question": question,
                                "interrupt_id": interrupt_id,
                                "interrupt_key": main_interrupt_key,
                                "source": "recommend_project",
                            },
                            agent_path=agent_path,
                            parent_tool_call_id=parent_tool_call_id,
                        ))

                config = get_temporal_config()
                response: dict[str, Any] = await _do_interrupt(
                    temporal_client,
                    key=main_interrupt_key,
                    callback=_emit_interrupt,
                    data={"question": question, "type": "select"},
                    task_queue=config.interrupt_task_queue,
                )

                user_reply: str = response.get("reply", "")

                # 把用户选择通过 A2A 传回 SubAgent
                result = await _a2a_send(
                    client, context_id, user_reply, task_id=task_id,
                )
            else:
                break

    return "".join(final_text_parts) if final_text_parts else "RecommendProject 执行完成"


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

    request_body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {"message": msg},
    }

    resp: httpx.Response = await client.post(
        f"{RECOMMEND_PROJECT_URL}/a2a", json=request_body,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

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

    artifacts: list[dict[str, Any]] = task_result.get("artifacts", [])
    for artifact in artifacts:
        art_id: str = artifact.get("artifactId", "") or artifact.get("index", "")
        if emitted_ids is not None and art_id:
            if art_id in emitted_ids:
                continue
            emitted_ids.add(art_id)
        parts: list[dict[str, Any]] = artifact.get("parts", [])
        for part in parts:
            kind: str = part.get("kind", "") or part.get("type", "")
            if kind == "text":
                text: str = part.get("text", "")
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
                data: dict[str, Any] = part.get("data", {})
                event_type: str = data.get("event_type", "")

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
        parts: list[dict[str, Any]] = msg.get("parts", [])
        texts: list[str] = []
        for part in parts:
            kind: str = part.get("kind", "") or part.get("type", "")
            if kind == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts) if texts else str(msg)
    return str(msg)

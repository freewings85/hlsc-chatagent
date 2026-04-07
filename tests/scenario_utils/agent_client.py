"""MainAgent SSE 客户端 — 发消息、解析事件流"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

MAINAGENT_URL: str = "http://127.0.0.1:8100"
DEFAULT_TIMEOUT: int = 120


@dataclass
class AgentResponse:
    """一次 SSE 交互的完整结果。"""

    text: str = ""
    tool_calls: list[str] = field(default_factory=list)
    specs: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    interrupt: dict[str, Any] | None = None
    error: str = ""
    elapsed_seconds: float = 0.0
    raw_events: list[dict[str, Any]] = field(default_factory=list)


async def send_message(
    session_id: str,
    user_id: str,
    message: str,
    context: dict[str, Any] | None = None,
    base_url: str = MAINAGENT_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> AgentResponse:
    """调用 /chat/stream SSE 端点，解析完整事件流并返回结构化结果。"""
    start: float = time.monotonic()
    result: AgentResponse = AgentResponse()

    text_parts: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(timeout))) as client:
            request_body: dict[str, Any] = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            if context is not None:
                request_body["context"] = context

            async with client.stream(
                "POST",
                f"{base_url}/chat/stream",
                json=request_body,
            ) as resp:
                resp.raise_for_status()
                buffer: str = ""

                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        raw_event: str
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event_type: str = ""
                        event_data: str = ""

                        for line in raw_event.strip().split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:].strip()
                            elif line.startswith("data: "):
                                event_data = line[6:]

                        if not event_data:
                            continue

                        try:
                            data: dict[str, Any] = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict[str, Any] = data.get("data", {})
                        result.raw_events.append({"type": event_type, "data": evt_data})

                        if event_type == "text":
                            content: str = str(evt_data.get("content", ""))
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = str(evt_data.get("tool_name", "unknown"))
                            result.tool_calls.append(tool_name)

                        elif event_type == "spec":
                            result.specs.append(evt_data)

                        elif event_type == "action":
                            result.actions.append(evt_data)

                        elif event_type == "interrupt":
                            result.interrupt = evt_data

                        elif event_type == "error":
                            err_msg: str = str(
                                evt_data.get("message", evt_data.get("error", str(evt_data)))
                            )
                            result.error = err_msg

                        elif event_type == "chat_request_end":
                            break

    except httpx.ReadTimeout:
        if not text_parts and not result.tool_calls:
            result.error = f"超时（{timeout}s），无任何响应"
    except httpx.ConnectError as e:
        result.error = f"连接失败: {e}"
    except Exception as e:
        if not text_parts and not result.tool_calls:
            result.error = str(e)

    result.text = "".join(text_parts)
    result.elapsed_seconds = time.monotonic() - start
    return result


def extract_tools_called(response: AgentResponse) -> list[str]:
    """提取调用的工具名列表。"""
    return response.tool_calls


def extract_text_response(response: AgentResponse) -> str:
    """提取拼接后的文本回复。"""
    return response.text


def extract_interrupt(response: AgentResponse) -> dict[str, Any] | None:
    """提取 interrupt 事件（如果有）。"""
    return response.interrupt

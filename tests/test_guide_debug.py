"""调试版 - 打印完整响应"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

import httpx

BASE_URL: str = "http://localhost:8100"
TIMEOUT: int = 60


async def send_message_verbose(session_id: str, message: str, user_id: str) -> None:
    """调用 /chat/stream，打印所有事件。"""
    print(f"\n用户消息: {message}")
    print(f"Session: {session_id}")
    print("=" * 70)

    text_parts: list[str] = []
    tool_calls: list[str] = []
    start: float = time.monotonic()
    event_count: int = 0

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(TIMEOUT))) as client:
            request_body: dict = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat/stream",
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
                            data: dict = json.loads(event_data)
                        except json.JSONDecodeError as e:
                            print(f"  [解析错误] {e}: {event_data[:100]}")
                            continue

                        evt_data: dict = data.get("data", {})
                        event_count += 1

                        if event_type == "text":
                            content: str = evt_data.get("content", "")
                            if content:
                                text_parts.append(content)
                                print(f"  [text #{event_count}] {content[:100]}")

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_calls.append(tool_name)
                            print(f"  [tool_call_start #{event_count}] {tool_name}")

                        elif event_type == "error":
                            err_msg: str = evt_data.get(
                                "message", evt_data.get("error", str(evt_data)),
                            )
                            print(f"  [error #{event_count}] {err_msg}")

    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return

    elapsed: float = time.monotonic() - start

    print(f"\n工具调用: {tool_calls if tool_calls else '(无)'}")
    print(f"完整回复: {repr(''.join(text_parts)[:200])}")
    print(f"事件总数: {event_count}")
    print(f"耗时: {elapsed:.1f}s")
    print("=" * 70)


async def main() -> None:
    """测试保险和车型两个问题场景。"""
    # 健康检查
    try:
        resp: httpx.Response = httpx.get(f"{BASE_URL}/health", timeout=5)
        print(f"✓ 服务就绪\n")
    except Exception as e:
        print(f"✗ 服务不可达: {e}")
        return

    # 场景 7: 保险续保
    session_id: str = str(uuid4())
    user_id: str = f"debug-insurance-{uuid4().hex[:8]}"
    await send_message_verbose(session_id, "我的车险快到期了，需要续保", user_id)

    # 场景 11: 车型收集
    session_id = str(uuid4())
    user_id = f"debug-car-{uuid4().hex[:8]}"
    await send_message_verbose(session_id, "我想做保养，但我不知道自己的车具体是什么型号", user_id)


if __name__ == "__main__":
    asyncio.run(main())

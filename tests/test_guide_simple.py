"""简化版 guide 场景实时验证（调试用）"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

import httpx

BASE_URL: str = "http://localhost:8100"
TIMEOUT: int = 30


async def send_message(session_id: str, message: str, user_id: str) -> dict:
    """调用 /chat/stream，返回工具调用和文本。"""
    text_parts: list[str] = []
    tool_calls: list[str] = []
    start: float = time.monotonic()

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
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict = data.get("data", {})

                        if event_type == "text":
                            content: str = evt_data.get("content", "")
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_calls.append(tool_name)

    except Exception as e:
        return {"error": str(e), "text": "", "tools": [], "elapsed": 0.0}

    elapsed: float = time.monotonic() - start

    return {
        "error": "",
        "text": "".join(text_parts),
        "tools": tool_calls,
        "elapsed": elapsed,
    }


async def main() -> None:
    """逐个场景运行，实时输出。"""
    # 健康检查
    try:
        resp: httpx.Response = httpx.get(f"{BASE_URL}/health", timeout=5)
        print(f"✓ 服务就绪: {BASE_URL}\n")
    except Exception as e:
        print(f"✗ 服务不可达: {e}")
        return

    test_cases: list[tuple[str, str]] = [
        ("场景1: 闲聊打招呼", "你好"),
        ("场景2: 闲聊天气", "今天天气不错，阳光很好"),
        ("场景3: 模糊需求", "我车有点问题"),
        ("场景5: 项目识别", "想换机油"),
        ("场景7: 保险续保", "我的车险快到期了，需要续保"),
        ("场景9: 平台介绍", "你是谁？能做什么？"),
        ("场景10: 位置信息", "我在朝阳区，附近有什么好修理厂吗？"),
        ("场景11: 车型收集", "我想做保养，但我不知道自己的车具体是什么型号"),
        ("场景13: 电商拒绝", "能不能帮我在淘宝买个机油？"),
    ]

    for label, user_message in test_cases:
        print(f"\n{'─' * 70}")
        print(f"▶ {label}")
        print(f"  用户: {user_message}")

        session_id: str = str(uuid4())
        user_id: str = f"test-{uuid4().hex[:8]}"

        result: dict = await send_message(session_id, user_message, user_id)

        if result["error"]:
            print(f"  ✗ 错误: {result['error']}")
            continue

        print(f"  工具调用: {result['tools'] if result['tools'] else '(无)'}")
        print(f"  回复 (首150字): {result['text'][:150]}...")
        print(f"  耗时: {result['elapsed']:.1f}s")

    print(f"\n{'─' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())

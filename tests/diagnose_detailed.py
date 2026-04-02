"""
详细诊断：查看 Agent 完整回复和工具调用

检查：
1. Agent 对 searchcoupons 输入的完整回复
2. 工具调用顺序和参数
3. scene 路由是否正确
"""

import asyncio
import json
import time
from uuid import uuid4

import httpx


async def test_single_message(message: str) -> None:
    """测试单条消息，查看完整回复"""

    session_id: str = str(uuid4())
    user_id: str = f"diag-{uuid4().hex[:8]}"

    print(f"\n{'='*80}")
    print(f"输入: '{message}'")
    print(f"{'='*80}\n")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            request_body: dict = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }

            text_parts: list[str] = []
            tool_calls: list[dict] = []
            current_scene: str = ""

            async with client.stream(
                "POST",
                "http://127.0.0.1:8100/chat/stream",
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
                                print(f"[Agent]: {content}")

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_input: dict = evt_data.get("tool_input", {})
                            tool_calls.append({
                                "tool": tool_name,
                                "input": tool_input
                            })
                            print(f"\n[工具调用]: {tool_name}")
                            if tool_input:
                                print(f"  参数: {json.dumps(tool_input, ensure_ascii=False, indent=4)}")

                        elif event_type == "interrupt":
                            interrupt_type: str = evt_data.get("type", "")
                            print(f"\n[中断]: {interrupt_type}")

            print(f"\n{'='*80}")
            print(f"完整回复: {''.join(text_parts)}")
            print(f"{'='*80}")
            print(f"\n工具调用数: {len(tool_calls)}")
            for i, call in enumerate(tool_calls, 1):
                print(f"  {i}. {call['tool']}")

    except Exception as e:
        print(f"❌ 错误: {e}")


async def main() -> None:
    """运行诊断"""
    test_messages: list[str] = [
        "换机油有优惠吗？",
        "帮我查查轮胎的优惠。",
        "有什么优惠活动吗？",
    ]

    for msg in test_messages:
        await test_single_message(msg)
        await asyncio.sleep(1)  # 间隔 1 秒避免过快


if __name__ == "__main__":
    asyncio.run(main())

"""
详细诊断 SC-009：用户选择优惠并确认时间

检查为什么轮2没有调用 apply_coupon
"""

import asyncio
import json
import time
from uuid import uuid4

import httpx


async def test_sc009() -> None:
    """测试 SC-009 流程"""

    session_id: str = str(uuid4())
    user_id: str = f"sc009-{uuid4().hex[:8]}"

    print(f"\n{'='*80}")
    print(f"SC-009: 用户选择优惠并确认时间")
    print(f"{'='*80}\n")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 轮1：查优惠
        print("[轮1] 用户: '换机油有优惠吗？'\n")

        request_body: dict = {
            "session_id": session_id,
            "message": "换机油有优惠吗？",
            "user_id": user_id,
        }

        text_parts_1: list[str] = []
        tool_calls_1: list[str] = []

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
                            text_parts_1.append(content)

                    elif event_type == "tool_call_start":
                        tool_name: str = evt_data.get("tool_name", "unknown")
                        tool_calls_1.append(tool_name)
                        print(f"[工具] {tool_name}")

        print(f"\n[Agent 回复] {''.join(text_parts_1)[:200]}...")
        print(f"[工具调用数] {len(tool_calls_1)}: {', '.join(tool_calls_1)}\n")

        # 轮2：选优惠并指定时间
        print("[轮2] 用户: '我要这个机油 8 折的，下午 2 点去。'\n")

        request_body["message"] = "我要这个机油 8 折的，下午 2 点去。"

        text_parts_2: list[str] = []
        tool_calls_2: list[str] = []

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
                            text_parts_2.append(content)
                            print(f"[Agent]: {content}")

                    elif event_type == "tool_call_start":
                        tool_name: str = evt_data.get("tool_name", "unknown")
                        tool_input: dict = evt_data.get("tool_input", {})
                        tool_calls_2.append(tool_name)
                        print(f"[工具] {tool_name}")
                        if tool_input:
                            print(f"  参数: {json.dumps(tool_input, ensure_ascii=False, indent=2)}")

        print(f"\n[Agent 回复] {''.join(text_parts_2)[:200]}...")
        print(f"[工具调用数] {len(tool_calls_2)}: {', '.join(tool_calls_2) or '无'}\n")

        print(f"{'='*80}")
        print(f"分析")
        print(f"{'='*80}")
        print(f"轮1 工具: {', '.join(tool_calls_1)}")
        print(f"轮2 工具: {', '.join(tool_calls_2) or '无'}")

        if "apply_coupon" in tool_calls_2:
            print(f"\n✓ apply_coupon 被调用")
        else:
            print(f"\n✗ apply_coupon 未被调用")
            print(f"原因可能:")
            print(f"  1. Agent 未识别用户要申领优惠的意图")
            print(f"  2. Agent 缺少必要的参数（activity_id, shop_id, visit_time）")
            print(f"  3. Prompt 逻辑未清晰指示何时调用 apply_coupon")


if __name__ == "__main__":
    asyncio.run(test_sc009())

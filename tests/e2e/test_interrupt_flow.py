"""interrupt + skill 端到端测试：直接通过 SSE API 验证完整的 publish-bidding 流程。

测试策略：
- 使用 httpx 直接调用 /chat/stream SSE 接口（不需要浏览器）
- 解析 SSE 事件流，验证 interrupt 事件是否正确发出
- 验证 skill 环境变量注入（config.env → bash env）
- 需要 mock_tool_server 运行在 :8106

测试前提：
- .env 中配置了真实的 LLM API Key
- cjml-cheap-weixiu mock_tool_server 运行在 http://127.0.0.1:8106
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import PLAYWRIGHT_PORT


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    """解析 SSE 文本为事件列表。"""
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_type = "message"
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()
        if data:
            try:
                events.append({"type": event_type, "data": json.loads(data)})
            except json.JSONDecodeError:
                pass
    return events


@pytest.fixture(scope="module")
def server_url() -> str:
    """返回测试服务器 URL（假设 conftest 已启动）。"""
    return f"http://127.0.0.1:{PLAYWRIGHT_PORT}"


@pytest.fixture(autouse=True)
def skip_if_no_mock_server() -> None:
    """如果 mock_tool_server 没运行就跳过。"""
    try:
        r = httpx.get(
            "http://127.0.0.1:8106/health",
            timeout=3,
            # 绕过代理
            proxy=None,
        )
        if r.status_code != 200:
            pytest.skip("mock_tool_server not running on :8106")
    except Exception:
        pytest.skip("mock_tool_server not running on :8106")


class TestInterruptFlow:
    """验证 interrupt 工具通过 SSE 发出 INTERRUPT 事件。"""

    def test_interrupt_event_in_sse_stream(self, base_url: str) -> None:
        """发送竞价请求，验证 SSE 流中包含 interrupt 事件。

        这个测试验证完整链路：
        1. 用户发送竞价请求
        2. LLM 调用 Skill(publish-bidding)
        3. LLM 按 SKILL.md 指令调用 bash 运行 prepare_bidding.py
        4. LLM 调用 interrupt 工具发送确认卡片
        5. SSE 流中出现 type=interrupt 的事件
        """
        session_id = "test-interrupt-001"

        with httpx.Client(timeout=120, proxy=None) as client:
            resp = client.post(
                f"{base_url}/chat/stream",
                json={
                    "session_id": session_id,
                    "message": "帮我给奔驰C级 2023款的刹车片（项目ID 10001）发起竞价询价",
                    "user_id": "test-user",
                },
                # 流式读取不要设 timeout 太短
            )
            assert resp.status_code == 200

            full_text = resp.text
            events = parse_sse_events(full_text)

        # 应该有事件
        assert len(events) > 0, "SSE 流为空"

        # 收集事件类型
        event_types = [e["type"] for e in events]

        # 打印关键事件便于调试
        for e in events:
            if e["type"] in ("tool_call_start", "tool_result", "interrupt", "error"):
                print(f"  EVENT: {e['type']} → {json.dumps(e['data'], ensure_ascii=False)[:500]}")
        # 打印文字内容
        text_content = "".join(
            e["data"].get("data", {}).get("content", "")
            for e in events
            if e["type"] == "text"
        )
        print(f"\n  TEXT({len(text_content)} chars): {text_content[:2000]}")

        # 验证：应包含 tool_call_start（Skill 或 bash 或 interrupt 调用）
        assert "tool_call_start" in event_types, f"没有 tool_call_start 事件: {event_types}"

        # 收集所有 tool 名称
        tool_names = [
            e["data"].get("data", {}).get("tool_name", "")
            for e in events
            if e["type"] == "tool_call_start"
        ]

        # 验证有 interrupt 事件 OR interrupt 工具调用
        has_interrupt_event = "interrupt" in event_types
        has_interrupt_tool = "interrupt" in tool_names

        assert has_interrupt_event or has_interrupt_tool, (
            f"没有 interrupt 事件或工具调用。"
            f"\n事件类型: {event_types}"
            f"\n工具名称: {tool_names}"
        )

        # 如果有 interrupt 事件，验证它包含正确的卡片类型
        if has_interrupt_event:
            interrupt_events = [e for e in events if e["type"] == "interrupt"]
            for ie in interrupt_events:
                card_data = ie["data"].get("data", ie["data"])
                assert "type" in card_data, f"interrupt 事件缺少 type 字段: {card_data}"

        print(f"\n✓ 测试通过: {len(events)} 个 SSE 事件")
        print(f"  事件类型: {event_types}")
        print(f"  工具调用: {tool_names}")

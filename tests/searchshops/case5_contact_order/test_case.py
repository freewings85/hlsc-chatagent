"""SS-005: 联系单生成 — 测试用例（多轮）"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchshops.case5_contact_order.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_contact_order() -> bool:
    """测试联系单生成（多轮）。"""
    session_id: str = f"ss005-{uuid4().hex[:8]}"
    user_id: str = "test-ss005"
    passed: bool = True

    print(f"\n{_B}SS-005: 联系单生成{_0}")
    print(f"  session: {session_id}")

    # 轮 1：搜索门店
    print(f"\n  {_B}轮 1: 搜索门店{_0}")
    r1: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="附近有什么修理厂",
        context=USER_CONTEXT,
    )

    if r1.error:
        print(f"  {_R}ERROR: {r1.error}{_0}")
        return False

    print(f"  耗时: {r1.elapsed_seconds:.1f}s | 工具: {r1.tool_calls}")

    if "search_shops" in r1.tool_calls:
        print(f"  {_G}PASS: 轮1 调了 search_shops{_0}")
    else:
        print(f"  {_R}FAIL: 轮1 未调 search_shops{_0}")
        passed = False

    # 轮 2：选店 + 时间 → 联系单
    print(f"\n  {_B}轮 2: 选店生成联系单{_0}")
    r2: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="就第一家，明天下午2点去",
    )

    if r2.error:
        print(f"  {_R}ERROR: {r2.error}{_0}")
        return False

    print(f"  耗时: {r2.elapsed_seconds:.1f}s | 工具: {r2.tool_calls}")
    print(f"  回复: {r2.text[:200]}{'...' if len(r2.text) > 200 else ''}")

    # 验证：调了 create_contact_order
    if "create_contact_order" in r2.tool_calls:
        print(f"  {_G}PASS: 调了 create_contact_order{_0}")
    else:
        # Agent 可能先追问确认
        confirm_keywords: list[str] = ["确认", "确定", "途虎", "第一家"]
        has_confirm: bool = any(kw in r2.text for kw in confirm_keywords)
        if has_confirm:
            print(f"  {_Y}WARN: 未调 create_contact_order，但在追问确认（合理路径）{_0}")
        else:
            print(f"  {_R}FAIL: 未调 create_contact_order 也未追问{_0}")
            passed = False

    # 验证：有回复文本
    if r2.text.strip():
        print(f"  {_G}PASS: 有回复文本{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    return passed


async def main() -> None:
    ok: bool = await test_contact_order()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SS-005 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

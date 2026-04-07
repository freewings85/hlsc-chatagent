"""SC-003: 预订优惠 — 测试用例（多轮）"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchcoupons.case3_book_coupon.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_book_coupon() -> bool:
    """测试预订优惠。"""
    session_id: str = f"sc003-{uuid4().hex[:8]}"
    user_id: str = "test-sc003"
    passed: bool = True

    print(f"\n{_B}SC-003: 预订优惠{_0}")
    print(f"  session: {session_id}")

    # 轮 1：查优惠
    print(f"\n  {_B}轮 1: 查机油优惠{_0}")
    r1: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="换机油有优惠吗？",
        context=USER_CONTEXT,
    )

    if r1.error:
        print(f"  {_R}ERROR: {r1.error}{_0}")
        return False

    print(f"  耗时: {r1.elapsed_seconds:.1f}s | 工具: {r1.tool_calls}")

    if "search_coupon" in r1.tool_calls:
        print(f"  {_G}PASS: 轮1 调了 search_coupon{_0}")
    else:
        print(f"  {_R}FAIL: 轮1 未调 search_coupon{_0}")
        passed = False

    # 轮 2：选优惠 + 给时间
    print(f"\n  {_B}轮 2: 选优惠下单{_0}")
    r2: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="我要这个八折的，明天下午2点去",
    )

    if r2.error:
        print(f"  {_R}ERROR: {r2.error}{_0}")
        return False

    print(f"  耗时: {r2.elapsed_seconds:.1f}s | 工具: {r2.tool_calls}")
    print(f"  回复: {r2.text[:200]}{'...' if len(r2.text) > 200 else ''}")

    # 验证：调了 book_coupon 或 apply_coupon 或 confirm_booking
    booking_tools: list[str] = ["book_coupon", "apply_coupon", "confirm_booking"]
    if any(t in r2.tool_calls for t in booking_tools):
        print(f"  {_G}PASS: 调了预订/申请工具{_0}")
    else:
        # Agent 可能追问确认
        if "确认" in r2.text or "确定" in r2.text:
            print(f"  {_Y}WARN: 未调预订工具，但在追问确认（合理路径）{_0}")
        else:
            print(f"  {_R}FAIL: 未调预订/申请工具也未追问{_0}")
            passed = False

    # 验证：有回复
    if r2.text.strip():
        print(f"  {_G}PASS: 有回复文本{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    return passed


async def main() -> None:
    ok: bool = await test_book_coupon()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SC-003 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

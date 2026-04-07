"""SC-002: 语义搜索优惠 — 测试用例（多轮）"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchcoupons.case2_semantic_search.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_semantic_search() -> bool:
    """测试语义搜索优惠（多轮累积）。"""
    session_id: str = f"sc002-{uuid4().hex[:8]}"
    user_id: str = "test-sc002"
    passed: bool = True

    print(f"\n{_B}SC-002: 语义搜索优惠{_0}")
    print(f"  session: {session_id}")

    # 轮 1
    print(f"\n  {_B}轮 1: 查机油优惠{_0}")
    r1: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="帮我看看换机油的优惠",
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

    # 轮 2：追加语义偏好
    print(f"\n  {_B}轮 2: 追加支付宝偏好{_0}")
    r2: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="要支付宝的活动",
    )

    if r2.error:
        print(f"  {_R}ERROR: {r2.error}{_0}")
        return False

    print(f"  耗时: {r2.elapsed_seconds:.1f}s | 工具: {r2.tool_calls}")
    print(f"  回复: {r2.text[:200]}{'...' if len(r2.text) > 200 else ''}")

    if "search_coupon" in r2.tool_calls:
        print(f"  {_G}PASS: 轮2 再次调了 search_coupon（带新偏好）{_0}")
    else:
        print(f"  {_Y}WARN: 轮2 未重新调 search_coupon{_0}")

    # 验证：有回复文本
    if r2.text.strip():
        print(f"  {_G}PASS: 有回复文本{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    return passed


async def main() -> None:
    ok: bool = await test_semantic_search()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SC-002 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

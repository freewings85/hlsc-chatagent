"""SS-002: 按商户类型筛选 — 测试用例"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchshops.case2_filter_by_type.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_filter_by_type() -> bool:
    """测试按商户类型筛选。"""
    session_id: str = f"ss002-{uuid4().hex[:8]}"
    user_id: str = "test-ss002"
    passed: bool = True

    print(f"\n{_B}SS-002: 按商户类型筛选{_0}")
    print(f"  session: {session_id}")

    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="附近有没有4S店",
        context=USER_CONTEXT,
    )

    if r.error:
        print(f"  {_R}ERROR: {r.error}{_0}")
        return False

    print(f"  耗时: {r.elapsed_seconds:.1f}s")
    print(f"  工具: {r.tool_calls}")
    print(f"  回复: {r.text[:200]}{'...' if len(r.text) > 200 else ''}")

    # 验证 1：调了 search_shops
    if "search_shops" in r.tool_calls:
        print(f"  {_G}PASS: 调了 search_shops{_0}")
    else:
        print(f"  {_R}FAIL: 未调 search_shops{_0}")
        passed = False

    # 验证 2：回复中包含 4S 店
    if "宝诚" in r.text or "4S" in r.text or "4s" in r.text:
        print(f"  {_G}PASS: 回复包含 4S 店信息{_0}")
    else:
        print(f"  {_Y}WARN: 回复中未见 4S 店关键词{_0}")

    # 验证 3：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    return passed


async def main() -> None:
    ok: bool = await test_filter_by_type()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SS-002 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

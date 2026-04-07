"""SC-001: 按项目查优惠 — 测试用例"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchcoupons.case1_search_by_project.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_search_by_project() -> bool:
    """测试按项目查优惠。"""
    session_id: str = f"sc001-{uuid4().hex[:8]}"
    user_id: str = "test-sc001"
    passed: bool = True

    print(f"\n{_B}SC-001: 按项目查优惠{_0}")
    print(f"  session: {session_id}")

    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="换机油有优惠吗？",
        context=USER_CONTEXT,
    )

    if r.error:
        print(f"  {_R}ERROR: {r.error}{_0}")
        return False

    print(f"  耗时: {r.elapsed_seconds:.1f}s")
    print(f"  工具: {r.tool_calls}")
    print(f"  回复: {r.text[:200]}{'...' if len(r.text) > 200 else ''}")

    # 验证 1：调了 search_coupon
    if "search_coupon" in r.tool_calls:
        print(f"  {_G}PASS: 调了 search_coupon{_0}")
    else:
        print(f"  {_R}FAIL: 未调 search_coupon{_0}")
        passed = False

    # 验证 2：调了 classify_project（机油关键词匹配项目）
    project_tools: list[str] = ["classify_project", "match_project"]
    if any(t in r.tool_calls for t in project_tools):
        print(f"  {_G}PASS: 调了项目分类工具{_0}")
    else:
        print(f"  {_Y}WARN: 未调 classify_project（Agent 可能直接传关键词搜索）{_0}")

    # 验证 3：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    # 验证 4：回复涉及优惠信息
    coupon_keywords: list[str] = ["优惠", "折", "减", "活动", "机油", "保养"]
    if any(kw in r.text for kw in coupon_keywords):
        print(f"  {_G}PASS: 回复包含优惠相关信息{_0}")
    else:
        print(f"  {_Y}WARN: 回复中未见优惠关键词{_0}")

    return passed


async def main() -> None:
    ok: bool = await test_search_by_project()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SC-001 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

"""SS-003: 按项目搜索门店 — 测试用例"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchshops.case3_search_by_project.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_search_by_project() -> bool:
    """测试按项目搜索门店。"""
    session_id: str = f"ss003-{uuid4().hex[:8]}"
    user_id: str = "test-ss003"
    passed: bool = True

    print(f"\n{_B}SS-003: 按项目搜索门店{_0}")
    print(f"  session: {session_id}")

    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="哪家店能换轮胎",
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

    # 验证 2：调了 match_project（可能名字不同，也检查 classify_project）
    project_tools: list[str] = ["match_project", "classify_project"]
    if any(t in r.tool_calls for t in project_tools):
        print(f"  {_G}PASS: 调了项目匹配工具{_0}")
    else:
        print(f"  {_Y}WARN: 未调 match_project/classify_project（Agent 可能直接搜索）{_0}")

    # 验证 3：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    # 验证 4：回复涉及轮胎相关
    if "轮胎" in r.text or "途虎" in r.text:
        print(f"  {_G}PASS: 回复包含轮胎/门店相关信息{_0}")
    else:
        print(f"  {_Y}WARN: 回复中未见轮胎相关关键词{_0}")

    return passed


async def main() -> None:
    ok: bool = await test_search_by_project()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SS-003 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

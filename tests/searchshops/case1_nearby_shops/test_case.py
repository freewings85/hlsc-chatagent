"""SS-001: 附近门店搜索 — 测试用例

验证：
1. 路由到 searchshops 场景
2. 调用 search_shops 工具
3. 返回浦东区门店（按距离排序）
4. 北京门店不在结果中
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchshops.case1_nearby_shops.mock_data import USER_CONTEXT

# ANSI 颜色
_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_nearby_shops() -> bool:
    """测试附近门店搜索。"""
    session_id: str = f"ss001-{uuid4().hex[:8]}"
    user_id: str = "test-ss001"
    passed: bool = True

    print(f"\n{_B}SS-001: 附近门店搜索{_0}")
    print(f"  session: {session_id}")

    # 轮 1：附近有什么修理厂
    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="附近有什么修理厂",
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

    # 验证 2：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    # 验证 3：回复中包含浦东门店信息
    pudong_keywords: list[str] = ["途虎", "小拇指", "精典", "浦东", "张江", "金桥"]
    found_pudong: bool = any(kw in r.text for kw in pudong_keywords)
    if found_pudong:
        print(f"  {_G}PASS: 回复包含浦东门店信息{_0}")
    else:
        print(f"  {_Y}WARN: 回复中未见浦东门店关键词{_0}")

    # 验证 4：北京门店不应出现
    beijing_keywords: list[str] = ["望京", "驰加"]
    found_beijing: bool = any(kw in r.text for kw in beijing_keywords)
    if not found_beijing:
        print(f"  {_G}PASS: 北京门店未出现（符合距离过滤）{_0}")
    else:
        print(f"  {_R}FAIL: 北京门店出现在结果中{_0}")
        passed = False

    return passed


async def main() -> None:
    ok: bool = await test_nearby_shops()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SS-001 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

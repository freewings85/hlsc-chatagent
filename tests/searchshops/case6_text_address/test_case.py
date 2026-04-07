"""SS-006: 文字地址搜索 — 测试用例"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchshops.case6_text_address.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_text_address() -> bool:
    """测试文字地址搜索。"""
    session_id: str = f"ss006-{uuid4().hex[:8]}"
    user_id: str = "test-ss006"
    passed: bool = True

    print(f"\n{_B}SS-006: 文字地址搜索{_0}")
    print(f"  session: {session_id}")

    # 不传 context（或空 context），用户用文字说地址
    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="南京西路附近有什么修理厂",
        context=USER_CONTEXT if USER_CONTEXT else None,
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

    # 验证 2：不应 interrupt（用户已给文字地址）
    if r.interrupt is None:
        print(f"  {_G}PASS: 无 interrupt（文字地址解析成功）{_0}")
    else:
        print(f"  {_Y}WARN: 有 interrupt（可能 address service 解析失败）{_0}")

    # 验证 3：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    # 验证 4：回复涉及南京西路/静安区相关
    location_keywords: list[str] = ["南京西路", "静安", "途虎", "小拇指"]
    if any(kw in r.text for kw in location_keywords):
        print(f"  {_G}PASS: 回复包含南京西路区域门店信息{_0}")
    else:
        print(f"  {_Y}WARN: 回复中未见南京西路相关关键词{_0}")

    return passed


async def main() -> None:
    ok: bool = await test_text_address()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SS-006 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

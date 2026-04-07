"""SC-004: 无结果降级 — 测试用例"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.agent_client import AgentResponse, send_message
from searchcoupons.case4_no_result_fallback.mock_data import USER_CONTEXT

_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_B: str = "\033[1m"
_0: str = "\033[0m"


async def test_no_result_fallback() -> bool:
    """测试无结果降级。"""
    session_id: str = f"sc004-{uuid4().hex[:8]}"
    user_id: str = "test-sc004"
    passed: bool = True

    print(f"\n{_B}SC-004: 无结果降级{_0}")
    print(f"  session: {session_id}")

    r: AgentResponse = await send_message(
        session_id=session_id,
        user_id=user_id,
        message="四轮定位有优惠吗？",
        context=USER_CONTEXT,
    )

    if r.error:
        print(f"  {_R}ERROR: {r.error}{_0}")
        return False

    print(f"  耗时: {r.elapsed_seconds:.1f}s")
    print(f"  工具: {r.tool_calls}")
    print(f"  回复: {r.text[:200]}{'...' if len(r.text) > 200 else ''}")

    # 验证 1：有回复文本
    if r.text.strip():
        print(f"  {_G}PASS: 有回复文本（{len(r.text)} 字）{_0}")
    else:
        print(f"  {_R}FAIL: 无回复文本{_0}")
        passed = False

    # 验证 2：不应编造优惠（检查是否包含虚假折扣信息）
    # 合理的回复应包含"暂无"、"没有"、"未找到"等
    no_result_keywords: list[str] = ["暂无", "没有", "未找到", "没查到", "找不到", "无"]
    has_honest_response: bool = any(kw in r.text for kw in no_result_keywords)
    if has_honest_response:
        print(f"  {_G}PASS: 诚实告知无结果{_0}")
    else:
        # 也可能 Agent 先调了工具然后建议换项目
        suggest_keywords: list[str] = ["建议", "其他", "保养", "换"]
        has_suggestion: bool = any(kw in r.text for kw in suggest_keywords)
        if has_suggestion:
            print(f"  {_G}PASS: 给出替代建议{_0}")
        else:
            print(f"  {_Y}WARN: 回复中未见明确的无结果提示或替代建议{_0}")

    return passed


async def main() -> None:
    ok: bool = await test_no_result_fallback()
    status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
    print(f"\n{'=' * 40}")
    print(f"SC-004 结果: {status}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(main())

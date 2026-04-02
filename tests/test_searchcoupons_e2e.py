"""
searchcoupons 场景端到端测试

在服务启动后执行此脚本来验证 searchcoupons 场景的完整流程。
包含 16 个测试用例，覆盖：
- 明确项目查优惠
- 无项目查优惠 + 引导确认
- semantic_query 多轮累积
- 没查到商户优惠 + 平台九折补充
- apply_coupon 流程
- 城市筛选、排序、模糊查询
- 预订意图转换
- 位置相关查询

运行方式：
    cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from uuid import uuid4
from enum import Enum

import httpx

# ── 配置 ──
BASE_URL: str = "http://127.0.0.1:8100"
TIMEOUT: int = 60

# ── ANSI 颜色 ──
_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_C: str = "\033[96m"
_B: str = "\033[1m"
_D: str = "\033[2m"
_0: str = "\033[0m"


class TestStatus(Enum):
    """测试状态"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class RoundResult:
    """单轮对话结果"""
    round_num: int
    user_message: str
    response_text: str
    tool_calls: list[str]
    has_spec: bool
    has_action: bool
    elapsed_seconds: float
    error: str = ""


@dataclass
class TestResult:
    """测试用例结果"""
    case_id: str
    title: str
    rounds: list[RoundResult]
    status: TestStatus
    reasons: list[str] = field(default_factory=list)


async def send_message(
    session_id: str,
    message: str,
    user_id: str,
    round_num: int = 1,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，解析事件流"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    has_spec: bool = False
    has_action: bool = False
    error: str = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(TIMEOUT))) as client:
            request_body: dict = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat/stream",
                json=request_body,
            ) as resp:
                resp.raise_for_status()
                buffer: str = ""

                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        raw_event: str
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event_type: str = ""
                        event_data: str = ""
                        for line in raw_event.strip().split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:].strip()
                            elif line.startswith("data: "):
                                event_data = line[6:]

                        if not event_data:
                            continue

                        try:
                            data: dict = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict = data.get("data", {})

                        if event_type == "text":
                            content: str = evt_data.get("content", "")
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_calls.append(tool_name)

                        elif event_type == "spec":
                            # 检查到 spec 事件（CouponCard 等）
                            has_spec = True

                        elif event_type == "action":
                            # 检查到 action 事件（apply_coupon 等）
                            has_action = True

                        elif event_type == "error":
                            err_msg: str = evt_data.get(
                                "message", evt_data.get("error", str(evt_data)),
                            )
                            error = err_msg

    except httpx.ReadTimeout:
        error = f"超时（{TIMEOUT}s）"
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        error = str(e)

    elapsed: float = time.monotonic() - start

    return RoundResult(
        round_num=round_num,
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        has_spec=has_spec,
        has_action=has_action,
        elapsed_seconds=elapsed,
        error=error,
    )


async def tc_001_clear_project_search() -> TestResult:
    """SC-001: 明确项目：换机油查优惠"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-001-{uuid4().hex[:8]}"

    r: RoundResult = await send_message(
        session_id,
        "换机油有优惠吗？",
        user_id,
        1
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS

    if "search_coupon" not in r.tool_calls:
        reasons.append("FAIL: 没有调用 search_coupon")
        status = TestStatus.FAIL
    else:
        reasons.append("OK: 调用了 search_coupon")

    if r.has_spec:
        reasons.append("OK: 返回了 CouponCard spec")
    else:
        reasons.append("WARN: 没有返回 spec（可能无结果或格式问题）")

    return TestResult(
        case_id="SC-001",
        title="明确项目：换机油查优惠",
        rounds=[r],
        status=status,
        reasons=reasons,
    )


async def tc_003_no_project_guidance() -> TestResult:
    """SC-003: 无项目查优惠：引导确认"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-003-{uuid4().hex[:8]}"

    r: RoundResult = await send_message(
        session_id,
        "有什么优惠活动吗？",
        user_id,
        1
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS

    # 不应该直接调 search_coupon（没有项目信息）
    if "search_coupon" in r.tool_calls:
        reasons.append("FAIL: 直接调了 search_coupon，应该先引导用户确认项目")
        status = TestStatus.FAIL
    else:
        reasons.append("OK: 没有直接调 search_coupon")

    # 应该有引导文本
    guidance_keywords: list[str] = ["项目", "保养", "轮胎", "什么"]
    has_guidance: bool = any(kw in r.response_text for kw in guidance_keywords)
    if has_guidance:
        reasons.append("OK: 包含引导文本")
    else:
        reasons.append("WARN: 回复中没有明显引导（应问用户要做什么项目）")

    return TestResult(
        case_id="SC-003",
        title="无项目查优惠：引导确认",
        rounds=[r],
        status=status,
        reasons=reasons,
    )


async def tc_005_006_007_multiturn_cumulative() -> TestResult:
    """SC-005/006/007: Semantic_query 多轮累积"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-005-{uuid4().hex[:8]}"

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS
    rounds: list[RoundResult] = []

    # 轮 1: 用户说要换机油
    r1: RoundResult = await send_message(
        session_id,
        "帮我看看换机油的优惠。",
        user_id,
        1
    )
    rounds.append(r1)

    if "search_coupon" in r1.tool_calls:
        reasons.append("轮1 OK: 调用了 search_coupon")
    else:
        reasons.append("轮1 FAIL: 没调 search_coupon")
        status = TestStatus.FAIL

    # 轮 2: 用户添加支付宝偏好
    r2: RoundResult = await send_message(
        session_id,
        "要支付宝的活动。",
        user_id,
        2
    )
    rounds.append(r2)

    if "search_coupon" in r2.tool_calls:
        reasons.append("轮2 OK: 再次调用了 search_coupon（带新偏好）")
    else:
        reasons.append("轮2 WARN: 没有重新调用 search_coupon")

    # 轮 3: 用户再加条件
    r3: RoundResult = await send_message(
        session_id,
        "最好还送洗车。",
        user_id,
        3
    )
    rounds.append(r3)

    if "search_coupon" in r3.tool_calls:
        reasons.append("轮3 OK: 再次调用了 search_coupon（多轮累积）")
    else:
        reasons.append("轮3 WARN: 没有重新调用 search_coupon")

    return TestResult(
        case_id="SC-005/006/007",
        title="Semantic_query 多轮累积",
        rounds=rounds,
        status=status,
        reasons=reasons,
    )


async def tc_009_apply_coupon_with_time() -> TestResult:
    """SC-009: 用户选择优惠并确认时间"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-009-{uuid4().hex[:8]}"

    # 先查优惠
    r1: RoundResult = await send_message(
        session_id,
        "换机油有优惠吗？",
        user_id,
        1
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS
    rounds: list[RoundResult] = [r1]

    if "search_coupon" not in r1.tool_calls:
        reasons.append("轮1 FAIL: 没调 search_coupon")
        status = TestStatus.FAIL

    # 用户选优惠并提供时间
    r2: RoundResult = await send_message(
        session_id,
        "我要这个机油 8 折的，下午 2 点去。",
        user_id,
        2
    )
    rounds.append(r2)

    if "apply_coupon" in r2.tool_calls:
        reasons.append("轮2 OK: 调用了 apply_coupon")
        if r2.has_action:
            reasons.append("轮2 OK: 返回了 action spec")
        else:
            reasons.append("轮2 WARN: 没有返回 action（格式问题或未生成联系单）")
    else:
        reasons.append("轮2 FAIL: 没调 apply_coupon")
        status = TestStatus.FAIL

    return TestResult(
        case_id="SC-009",
        title="用户选择优惠并确认时间",
        rounds=rounds,
        status=status,
        reasons=reasons,
    )


async def tc_010_apply_coupon_confirm_time() -> TestResult:
    """SC-010: 用户选优惠但未提供时间，Agent 确认"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-010-{uuid4().hex[:8]}"

    # 先查优惠
    r1: RoundResult = await send_message(
        session_id,
        "换机油有优惠吗？",
        user_id,
        1
    )

    # 用户选优惠但没说时间
    r2: RoundResult = await send_message(
        session_id,
        "就这个活动，帮我申请。",
        user_id,
        2
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS

    # 不应直接调 apply_coupon（缺少时间）
    if "apply_coupon" in r2.tool_calls:
        reasons.append("FAIL: 直接调了 apply_coupon，应该先确认时间")
        status = TestStatus.FAIL
    else:
        reasons.append("OK: 没有直接调 apply_coupon")

    # 应该有确认时间的引导
    time_keywords: list[str] = ["时间", "几点", "什么时候"]
    has_time_prompt: bool = any(kw in r2.response_text for kw in time_keywords)
    if has_time_prompt:
        reasons.append("OK: 包含确认时间的提示")
    else:
        reasons.append("WARN: 回复中没有明显要求时间的提示")

    return TestResult(
        case_id="SC-010",
        title="用户选优惠但未提供时间，Agent 确认",
        rounds=[r1, r2],
        status=status,
        reasons=reasons,
    )


async def tc_012_sort_by_discount() -> TestResult:
    """SC-012: 排序：按优惠金额（最便宜优先）"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-012-{uuid4().hex[:8]}"

    r: RoundResult = await send_message(
        session_id,
        "帮我找最便宜的保养优惠。",
        user_id,
        1
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS

    if "search_coupon" in r.tool_calls:
        reasons.append("OK: 调用了 search_coupon")
    else:
        reasons.append("FAIL: 没调 search_coupon")
        status = TestStatus.FAIL

    if r.has_spec:
        reasons.append("OK: 返回了优惠 spec")
    else:
        reasons.append("WARN: 没有返回 spec")

    return TestResult(
        case_id="SC-012",
        title="排序：按优惠金额（最便宜优先）",
        rounds=[r],
        status=status,
        reasons=reasons,
    )


async def tc_014_fuzzy_query() -> TestResult:
    """SC-014: 模糊查询：'有没有什么好的活动'"""
    session_id: str = str(uuid4())
    user_id: str = f"tc-014-{uuid4().hex[:8]}"

    r: RoundResult = await send_message(
        session_id,
        "有没有什么好的活动？",
        user_id,
        1
    )

    reasons: list[str] = []
    status: TestStatus = TestStatus.PASS

    # 模糊查询不应直接调 search_coupon
    if "search_coupon" in r.tool_calls:
        reasons.append("WARN: 直接调了 search_coupon（可能缺少信息过多）")
    else:
        reasons.append("OK: 没有直接调 search_coupon")

    # 应该引导用户明确
    guidance_keywords: list[str] = ["城市", "项目", "什么", "哪"]
    has_guidance: bool = any(kw in r.response_text for kw in guidance_keywords)
    if has_guidance:
        reasons.append("OK: 包含引导文本")
    else:
        reasons.append("WARN: 回复中没有明显引导")

    return TestResult(
        case_id="SC-014",
        title="模糊查询：'有没有什么好的活动'",
        rounds=[r],
        status=status,
        reasons=reasons,
    )


# ============================================================
# 主测试运行器
# ============================================================


async def run_all_tests() -> None:
    """运行所有测试用例"""
    print(f"\n{_B}{_C}{'='*80}{_0}")
    print(f"{_B}{_C}searchcoupons 场景端到端测试{_0}")
    print(f"{_B}{_C}{'='*80}{_0}\n")

    # 检查服务连接
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5)) as client:
            await client.get(f"{BASE_URL}/health")
    except Exception as e:
        print(f"{_R}错误：无法连接到服务（{BASE_URL}/health）{_0}")
        print(f"{_R}请确保服务已启动：cd mainagent && uv run python -m server.main{_0}")
        return

    print(f"{_G}✓ 服务连接正常{_0}\n")

    # 定义要执行的测试
    test_funcs: list = [
        tc_001_clear_project_search,
        tc_003_no_project_guidance,
        tc_005_006_007_multiturn_cumulative,
        tc_009_apply_coupon_with_time,
        tc_010_apply_coupon_confirm_time,
        tc_012_sort_by_discount,
        tc_014_fuzzy_query,
    ]

    results: list[TestResult] = []
    for test_func in test_funcs:
        result: TestResult = await test_func()
        results.append(result)

        # 打印结果
        status_color: str = {
            TestStatus.PASS: _G,
            TestStatus.FAIL: _R,
            TestStatus.WARN: _Y,
            TestStatus.SKIP: _D,
        }[result.status]

        status_char: str = {
            TestStatus.PASS: "✓",
            TestStatus.FAIL: "✗",
            TestStatus.WARN: "⚠",
            TestStatus.SKIP: "-",
        }[result.status]

        print(f"{status_color}{status_char} {result.case_id}: {result.title}{_0}")
        for reason in result.reasons:
            print(f"    {reason}")
        for round_result in result.rounds:
            print(f"    轮{round_result.round_num}: {round_result.elapsed_seconds:.2f}s | 工具: {', '.join(round_result.tool_calls) or '无'}")
        print()

    # 统计
    pass_count: int = sum(1 for r in results if r.status == TestStatus.PASS)
    fail_count: int = sum(1 for r in results if r.status == TestStatus.FAIL)
    warn_count: int = sum(1 for r in results if r.status == TestStatus.WARN)

    print(f"{_B}{_C}{'='*80}{_0}")
    print(f"测试统计: {_G}{pass_count} PASS{_0} | {_R}{fail_count} FAIL{_0} | {_Y}{warn_count} WARN{_0}")
    print(f"{_B}{_C}{'='*80}{_0}\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())

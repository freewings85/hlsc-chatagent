"""delegate skills 修复验证 + 非复合场景不受影响

测试 3 件事：
1. BMA /classify 端点分类准确性
2. 非复合场景（单场景）正常路由、工具调用
3. 复合场景走 orchestrator + delegate

运行方式：
    cd mainagent && uv run python ../tests/test_delegate_and_routing.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from uuid import uuid4

import httpx

# ── 配置 ──
MAINAGENT_URL: str = "http://127.0.0.1:8100"
BMA_URL: str = "http://127.0.0.1:8103"
TIMEOUT: int = 90

# ── ANSI 颜色 ──
_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_C: str = "\033[96m"
_B: str = "\033[1m"
_D: str = "\033[2m"
_0: str = "\033[0m"


# ============================================================
# 数据模型
# ============================================================


@dataclass
class RoundResult:
    """单轮对话结果。"""
    user_message: str
    response_text: str
    tool_calls: list[str]
    elapsed_seconds: float
    error: str = ""


@dataclass
class TestResult:
    """单个测试结果。"""
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    round_result: RoundResult | None = None


# ============================================================
# SSE 流式客户端（复用 test_s1_security.py 的解析逻辑）
# ============================================================


async def send_message(
    session_id: str,
    message: str,
    user_id: str = "test-delegate-user",
) -> RoundResult:
    """调用 /chat/stream SSE 端点，解析事件流。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
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
                f"{MAINAGENT_URL}/chat/stream",
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
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 测试 3：BMA /classify 端点验证
# ============================================================


async def test_bma_classify() -> list[TestResult]:
    """直接调 BMA /classify 验证场景分类。"""
    results: list[TestResult] = []

    classify_cases: list[tuple[str, list[str]]] = [
        ("我要洗个车", []),
        ("有什么优惠", ["searchcoupons"]),
        ("附近有什么修理厂", ["searchshops"]),
        ("帮我用九折券预订换机油", ["platform"]),
        ("保险到期了", ["insurance"]),
        ("帮我找个修理厂顺便看看优惠", ["searchshops", "searchcoupons"]),
    ]

    for message, expected_scenes in classify_cases:
        test_name: str = f"BMA分类: '{message}' → {expected_scenes}"
        details: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp: httpx.Response = await client.post(
                    f"{BMA_URL}/classify",
                    json={"message": message},
                )
                resp.raise_for_status()
                data: dict = resp.json()
                actual_scenes: list[str] = data.get("scenes", [])

            details.append(f"期望: {expected_scenes}")
            details.append(f"实际: {actual_scenes}")

            # 判定：场景集合匹配（顺序无关）
            passed: bool = set(actual_scenes) == set(expected_scenes)
            if not passed:
                details.append("FAIL: 场景不匹配")
            else:
                details.append("OK: 场景匹配")

        except Exception as e:
            passed = False
            actual_scenes = []
            details.append(f"ERROR: {e}")

        results.append(TestResult(name=test_name, passed=passed, details=details))

    return results


# ============================================================
# 测试 1：非复合场景（单场景路由）
# ============================================================


async def test_single_scene_routing() -> list[TestResult]:
    """单场景不走 orchestrator，工具调用正常。"""
    results: list[TestResult] = []

    single_cases: list[dict[str, str | list[str]]] = [
        {
            "message": "有什么优惠活动吗",
            "session_id": f"test-single-sc-{uuid4().hex[:8]}",
            "expect_scene": "searchcoupons",
            "expect_tools_any": ["search_coupon"],
            "expect_no_tools": ["delegate", "confirm_booking"],
        },
        {
            "message": "附近有什么修理厂",
            "session_id": f"test-single-ss-{uuid4().hex[:8]}",
            "expect_scene": "searchshops",
            "expect_tools_any": ["search_shops"],
            "expect_no_tools": ["delegate", "confirm_booking"],
        },
        {
            "message": "保险到期了",
            "session_id": f"test-single-ins-{uuid4().hex[:8]}",
            "expect_scene": "insurance",
            "expect_tools_any": [],  # insurance 可能先问问题
            "expect_no_tools": ["delegate", "search_coupon", "confirm_booking"],
        },
    ]

    for case in single_cases:
        message: str = str(case["message"])
        session_id: str = str(case["session_id"])
        expect_scene: str = str(case["expect_scene"])
        expect_tools_any: list[str] = list(case.get("expect_tools_any", []))
        expect_no_tools: list[str] = list(case.get("expect_no_tools", []))

        test_name: str = f"单场景({expect_scene}): '{message}'"
        details: list[str] = []

        r: RoundResult = await send_message(session_id, message)

        if r.error:
            details.append(f"ERROR: {r.error}")
            results.append(TestResult(name=test_name, passed=False, details=details, round_result=r))
            continue

        details.append(f"工具调用: {r.tool_calls}")
        details.append(f"回复长度: {len(r.response_text)} 字")
        details.append(f"耗时: {r.elapsed_seconds:.1f}s")

        passed: bool = True

        # 检查不该出现的工具
        forbidden_called: list[str] = [t for t in r.tool_calls if t in expect_no_tools]
        if forbidden_called:
            details.append(f"FAIL: 调了禁止工具: {forbidden_called}")
            passed = False
        else:
            details.append("OK: 未调禁止工具")

        # 特别检查 delegate — 单场景不应走 delegate
        if "delegate" in r.tool_calls:
            details.append("FAIL: 单场景走了 delegate（不应该）")
            passed = False

        # 检查有回复文本
        if not r.response_text.strip():
            details.append("FAIL: 无回复文本")
            passed = False
        else:
            details.append("OK: 有回复文本")

        # 如果指定了期望工具，至少调了一个
        if expect_tools_any:
            matched_tools: list[str] = [t for t in r.tool_calls if t in expect_tools_any]
            if matched_tools:
                details.append(f"OK: 调了期望工具 {matched_tools}")
            else:
                details.append(f"WARN: 未调期望工具 {expect_tools_any}（可能先问了问题）")

        results.append(TestResult(name=test_name, passed=passed, details=details, round_result=r))

    return results


# ============================================================
# 测试 2：复合场景（orchestrator + delegate）
# ============================================================


async def test_compound_scene_routing() -> list[TestResult]:
    """多场景走 orchestrator + delegate。"""
    results: list[TestResult] = []

    multi_cases: list[dict[str, str | list[str]]] = [
        {
            "message": "帮我找个修理厂，顺便看看有什么保养优惠",
            "session_id": f"test-multi-1-{uuid4().hex[:8]}",
            "expect_bma": ["searchshops", "searchcoupons"],
        },
        {
            "message": "有优惠的店有哪些",
            "session_id": f"test-multi-2-{uuid4().hex[:8]}",
            "expect_bma": ["searchshops", "searchcoupons"],
        },
    ]

    for case in multi_cases:
        message: str = str(case["message"])
        session_id: str = str(case["session_id"])
        expect_bma: list[str] = list(case.get("expect_bma", []))

        test_name: str = f"复合场景: '{message}'"
        details: list[str] = []

        # 先验证 BMA 确实返回多场景
        bma_scenes: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp: httpx.Response = await client.post(
                    f"{BMA_URL}/classify",
                    json={"message": message},
                )
                resp.raise_for_status()
                bma_data: dict = resp.json()
                bma_scenes = bma_data.get("scenes", [])
        except Exception as e:
            details.append(f"BMA 调用失败: {e}")

        details.append(f"BMA 分类: {bma_scenes}（期望 {expect_bma}）")

        bma_multi: bool = len(bma_scenes) > 1
        if bma_multi:
            details.append("OK: BMA 返回多场景")
        else:
            details.append(f"WARN: BMA 未返回多场景（实际: {bma_scenes}），orchestrator 可能不被触发")

        # 发 SSE 消息
        r: RoundResult = await send_message(session_id, message)

        if r.error:
            details.append(f"ERROR: {r.error}")
            results.append(TestResult(name=test_name, passed=False, details=details, round_result=r))
            continue

        details.append(f"工具调用: {r.tool_calls}")
        details.append(f"回复长度: {len(r.response_text)} 字")
        details.append(f"耗时: {r.elapsed_seconds:.1f}s")

        passed: bool = True

        # 如果 BMA 返回多场景，应该走 delegate
        if bma_multi:
            if "delegate" in r.tool_calls:
                delegate_count: int = r.tool_calls.count("delegate")
                details.append(f"OK: 走了 delegate（{delegate_count} 次）")
            else:
                details.append("FAIL: BMA 返回多场景但未调 delegate")
                passed = False

        # 检查有回复文本
        if not r.response_text.strip():
            details.append("FAIL: 无回复文本")
            passed = False
        else:
            details.append("OK: 有回复文本")

        # 检查子 agent 工具是否被调用（通过 delegate 内部）
        # delegate 内部的工具调用也会通过 emitter 传出
        sub_agent_tools: list[str] = [
            t for t in r.tool_calls
            if t not in ("delegate",) and t != "unknown"
        ]
        if sub_agent_tools:
            details.append(f"OK: 子 agent 调了工具: {sub_agent_tools}")
        else:
            details.append("WARN: 未观察到子 agent 工具调用（可能被 emitter 过滤）")

        results.append(TestResult(name=test_name, passed=passed, details=details, round_result=r))

    return results


# ============================================================
# 报告输出
# ============================================================


def print_report(
    section_name: str,
    results: list[TestResult],
) -> tuple[int, int]:
    """打印测试报告段落，返回 (passed, total)。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{_B}{'─' * 60}{_0}")
    print(f"{_B}{section_name}{_0}")
    print(f"{_B}{'─' * 60}{_0}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"  {status} {result.name}")

        for detail in result.details:
            if detail.startswith("FAIL") or detail.startswith("ERROR"):
                print(f"    {_R}{detail}{_0}")
            elif detail.startswith("WARN"):
                print(f"    {_Y}{detail}{_0}")
            elif detail.startswith("OK"):
                print(f"    {_G}{detail}{_0}")
            else:
                print(f"    {_D}{detail}{_0}")

        if result.round_result:
            r: RoundResult = result.round_result
            truncated: str = r.response_text[:150] + ("..." if len(r.response_text) > 150 else "")
            print(f"    {_D}回复: {truncated}{_0}")

        print()

    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"  {color}通过: {passed_count}/{total}{_0}\n")

    return passed_count, total


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行所有测试。"""
    # 健康检查
    try:
        r1: httpx.Response = httpx.get(f"{MAINAGENT_URL}/health", timeout=5)
        r1.raise_for_status()
        print(f"{_G}MainAgent 就绪: {MAINAGENT_URL}{_0}")
    except Exception as e:
        print(f"{_R}MainAgent 不可达: {MAINAGENT_URL} — {e}{_0}")
        return

    try:
        r2: httpx.Response = httpx.get(f"{BMA_URL}/health", timeout=5)
        r2.raise_for_status()
        print(f"{_G}BMA 就绪: {BMA_URL}{_0}")
    except Exception as e:
        print(f"{_R}BMA 不可达: {BMA_URL} — {e}{_0}")
        return

    print(f"\n{'=' * 60}")
    print(f"{_B}delegate skills 修复验证 + 场景路由测试{_0}")
    print(f"{'=' * 60}")

    total_passed: int = 0
    total_tests: int = 0

    # ── 测试 3：BMA classify ──
    print(f"\n{_C}>>> 运行测试 3：BMA /classify 分类验证...{_0}")
    bma_results: list[TestResult] = await test_bma_classify()
    p, t = print_report("测试 3：BMA /classify 分类验证", bma_results)
    total_passed += p
    total_tests += t

    # ── 测试 1：非复合场景 ──
    print(f"\n{_C}>>> 运行测试 1：非复合场景...{_0}")
    single_results: list[TestResult] = await test_single_scene_routing()
    p, t = print_report("测试 1：非复合场景（单场景路由）", single_results)
    total_passed += p
    total_tests += t

    # ── 测试 2：复合场景 ──
    print(f"\n{_C}>>> 运行测试 2：复合场景...{_0}")
    compound_results: list[TestResult] = await test_compound_scene_routing()
    p, t = print_report("测试 2：复合场景（orchestrator + delegate）", compound_results)
    total_passed += p
    total_tests += t

    # ── 汇总 ──
    print(f"\n{'=' * 60}")
    color: str = _G if total_passed == total_tests else _Y if total_passed > 0 else _R
    print(f"{color}{_B}总计: {total_passed}/{total_tests} 通过{_0}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())

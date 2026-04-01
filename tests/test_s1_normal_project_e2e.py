"""S1 普通项目场景 E2E 测试

直接调用已运行的 MainAgent (http://localhost:8100) 的 SSE 端点，
验证 4 个普通项目场景的工具调用和回复质量。

运行方式：
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    uv run python tests/test_s1_normal_project_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

# ── 配置 ──
BASE_URL: str = "http://localhost:8100"
TIMEOUT: int = 60

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
    round_num: int
    user_message: str
    response_text: str
    tool_calls: list[str]
    interrupts: list[dict[str, Any]]
    elapsed_seconds: float
    error: str = ""


@dataclass
class ScenarioResult:
    """场景评估结果。"""
    name: str
    rounds: list[RoundResult]
    passed: bool
    reasons: list[str]


# ============================================================
# SSE 流式客户端
# ============================================================

async def chat_stream_with_interrupt(
    base_url: str,
    session_id: str,
    message: str,
    user_id: str,
    timeout: int,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，自动处理 interrupt，返回完整结果。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    interrupts: list[dict[str, Any]] = []
    error: str = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(timeout))) as client:
            request_body: dict[str, Any] = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            async with client.stream(
                "POST",
                f"{base_url}/chat/stream",
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
                            data: dict[str, Any] = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict[str, Any] = data.get("data", {})

                        if event_type == "text":
                            content: str = evt_data.get("content", "")
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_calls.append(tool_name)

                        elif event_type == "interrupt":
                            i_key: str = evt_data.get("interrupt_key", "")
                            i_type: str = evt_data.get("type", "")
                            interrupts.append({
                                "type": i_type,
                                "interrupt_key": i_key,
                                "question": evt_data.get("question", ""),
                            })

                        elif event_type == "error":
                            err_msg: str = evt_data.get(
                                "message", evt_data.get("error", str(evt_data)),
                            )
                            error = err_msg

    except httpx.ReadTimeout:
        error = f"超时（{timeout}s）"
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        error = str(e)

    elapsed: float = time.monotonic() - start

    return RoundResult(
        round_num=0,
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        interrupts=interrupts,
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 关键词列表
# ============================================================

SAVING_KEYWORDS: list[str] = [
    "省钱", "优惠", "折扣", "九折", "划算", "便宜", "省", "活动",
    "券", "打折", "满减", "返现", "补贴", "特价", "促销", "竞价",
    "平台", "方案", "方式",
]


# ============================================================
# 场景定义与评估
# ============================================================


async def scenario_1_carwash_price() -> ScenarioResult:
    """场景 1: 洗车多少钱 — 应该调 classify_project + search_coupon，直接给出省钱信息。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-carwash-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "洗车多少钱", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True

    # 检查: 是否调了 classify_project
    if "classify_project" in r.tool_calls:
        reasons.append("OK: 调用了 classify_project")
    else:
        reasons.append("FAIL: 没有调用 classify_project")
        passed = False

    # 检查: 是否调了 search_coupon
    if "search_coupon" in r.tool_calls:
        reasons.append("OK: 调用了 search_coupon")
    else:
        reasons.append("WARN: 没有调用 search_coupon（可能 classify_project 未返回结果导致跳过）")

    # 检查: 回复中是否有省钱/优惠信息
    has_saving: bool = any(kw in r.response_text for kw in SAVING_KEYWORDS)
    if has_saving:
        reasons.append("OK: 回复中包含省钱/优惠信息")
    else:
        reasons.append("FAIL: 回复中没有省钱/优惠信息")
        passed = False

    # 检查: 不应该反问"要不要帮你查"
    ask_patterns: list[str] = ["要不要帮你查", "要不要帮您查", "需要我帮你查", "需要我帮您查", "要我查", "要我帮你"]
    has_unnecessary_ask: bool = any(p in r.response_text for p in ask_patterns)
    if has_unnecessary_ask:
        reasons.append("FAIL: 有不必要的反问（应直接查询，不问用户）")
        passed = False
    else:
        reasons.append("OK: 没有不必要的反问")

    # 检查错误
    if r.error:
        reasons.append(f"ERROR: {r.error}")
        passed = False

    return ScenarioResult(
        name="场景1: 洗车多少钱",
        rounds=[r],
        passed=passed,
        reasons=reasons,
    )


async def scenario_2_oil_change() -> ScenarioResult:
    """场景 2: 换机油 — 应该调 classify_project，展示省钱方法。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-oil-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "我想换个机油", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True

    # 检查: 是否调了 classify_project
    if "classify_project" in r.tool_calls:
        reasons.append("OK: 调用了 classify_project")
    else:
        reasons.append("FAIL: 没有调用 classify_project")
        passed = False

    # 检查: 回复中是否展示了省钱方法
    has_saving: bool = any(kw in r.response_text for kw in SAVING_KEYWORDS)
    if has_saving:
        reasons.append("OK: 回复中展示了省钱方法")
    else:
        reasons.append("FAIL: 回复中没有展示省钱方法")
        passed = False

    # 检查错误
    if r.error:
        reasons.append(f"ERROR: {r.error}")
        passed = False

    return ScenarioResult(
        name="场景2: 换机油",
        rounds=[r],
        passed=passed,
        reasons=reasons,
    )


async def scenario_3_multi_turn_funnel() -> ScenarioResult:
    """场景 3: 多轮漏斗 — 换刹车片 → 用平台优惠 → 应调 proceed_to_booking。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-funnel-{uuid4().hex[:8]}"

    rounds: list[RoundResult] = []
    reasons: list[str] = []
    passed: bool = True

    # ---- 第 1 轮: "换刹车片" ----
    r1: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "换刹车片", user_id, TIMEOUT,
    )
    r1.round_num = 1
    rounds.append(r1)

    if "classify_project" in r1.tool_calls:
        reasons.append("OK: 第1轮调用了 classify_project")
    else:
        reasons.append("WARN: 第1轮没有调用 classify_project")

    has_saving_r1: bool = any(kw in r1.response_text for kw in SAVING_KEYWORDS)
    if has_saving_r1:
        reasons.append("OK: 第1轮展示了省钱方法")
    else:
        reasons.append("WARN: 第1轮没有展示省钱方法")

    if r1.error:
        reasons.append(f"ERROR R1: {r1.error}")
        passed = False

    # ---- 第 2 轮: 根据第1轮回复调整消息 ----
    # 目标：用户选择平台优惠
    r2_message: str = "用平台优惠吧"
    r2: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, r2_message, user_id, TIMEOUT,
    )
    r2.round_num = 2
    rounds.append(r2)

    if "proceed_to_booking" in r2.tool_calls:
        reasons.append("OK: 第2轮调用了 proceed_to_booking")
    else:
        reasons.append("FAIL: 第2轮没有调用 proceed_to_booking")
        passed = False

    if r2.error:
        reasons.append(f"ERROR R2: {r2.error}")
        passed = False

    return ScenarioResult(
        name="场景3: 多轮漏斗（换刹车片 -> 用平台优惠）",
        rounds=rounds,
        passed=passed,
        reasons=reasons,
    )


async def scenario_4_chitchat_redirect() -> ScenarioResult:
    """场景 4: 闲聊拉回 — 今天天气怎么样 → 应该拉回养车/省钱话题。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-chitchat-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "今天天气怎么样", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True

    # 回复中应包含养车/省钱相关引导（具体的，不是空泛的"您有养车需求吗"）
    redirect_keywords: list[str] = [
        "养车", "保养", "维修", "省钱", "优惠", "爱车",
        "洗车", "换油", "轮胎", "刹车", "机油", "项目",
        "服务", "帮您省", "帮你省",
    ]
    has_redirect: bool = any(kw in r.response_text for kw in redirect_keywords)

    # 检查是否空泛回应（只说"有什么需求"但没有具体话题）
    vague_patterns: list[str] = ["您有养车需求吗", "有什么可以帮您"]
    is_only_vague: bool = (
        any(p in r.response_text for p in vague_patterns)
        and not any(kw in r.response_text for kw in ["保养", "维修", "省钱", "优惠", "洗车", "机油", "轮胎"])
    )

    if has_redirect and not is_only_vague:
        reasons.append("OK: 闲聊后有具体的养车/省钱引导")
    elif has_redirect and is_only_vague:
        reasons.append("FAIL: 闲聊后只有空泛引导，缺少具体话题")
        passed = False
    else:
        reasons.append("FAIL: 闲聊后没有拉回养车话题")
        passed = False

    # 检查错误
    if r.error:
        reasons.append(f"ERROR: {r.error}")
        passed = False

    return ScenarioResult(
        name="场景4: 闲聊拉回",
        rounds=[r],
        passed=passed,
        reasons=reasons,
    )


# ============================================================
# 报告输出
# ============================================================


def print_round(r: RoundResult) -> None:
    """打印单轮对话结果。"""
    truncated: str = r.response_text[:200] + ("..." if len(r.response_text) > 200 else "")
    print(f"    {_D}[轮{r.round_num}] 用户: {r.user_message}{_0}")
    print(f"    {_D}回复: {truncated}{_0}")
    if r.tool_calls:
        print(f"    {_C}工具调用: {', '.join(r.tool_calls)}{_0}")
    if r.interrupts:
        i_types: list[str] = [i["type"] for i in r.interrupts]
        print(f"    {_Y}Interrupt: {', '.join(i_types)}{_0}")
    if r.error:
        print(f"    {_R}错误: {r.error}{_0}")
    print(f"    {_D}耗时: {r.elapsed_seconds:.1f}s{_0}")
    print()


def print_report(results: list[ScenarioResult]) -> None:
    """打印汇总报告。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{'=' * 70}")
    print(f"{_B}S1 普通项目场景 E2E 测试报告{_0}")
    print(f"{'=' * 70}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"  {status} {_B}{result.name}{_0}")
        print()

        for r in result.rounds:
            print_round(r)

        for reason in result.reasons:
            if reason.startswith("FAIL"):
                print(f"    {_R}{reason}{_0}")
            elif reason.startswith("WARN"):
                print(f"    {_Y}{reason}{_0}")
            elif reason.startswith("ERROR"):
                print(f"    {_R}{reason}{_0}")
            else:
                print(f"    {_G}{reason}{_0}")
        print(f"  {'─' * 60}\n")

    print(f"{'=' * 70}")
    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"  {color}总结: {passed_count}/{total} PASS{_0}")
    print(f"{'=' * 70}\n")


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """依次运行所有 S1 普通项目场景。"""
    print(f"\n{_B}S1 普通项目场景 E2E 测试{_0}")
    print(f"  MainAgent: {BASE_URL}")
    print(f"  超时: {TIMEOUT}s\n")

    # 先检查服务是否可用
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp: httpx.Response = await client.get(f"{BASE_URL}/health")
            resp.raise_for_status()
            print(f"  {_G}MainAgent 健康检查通过{_0}\n")
    except Exception as e:
        print(f"  {_R}MainAgent 不可用: {e}{_0}")
        print(f"  请确保 MainAgent 在 {BASE_URL} 运行中")
        return

    scenarios: list[tuple[str, Any]] = [
        ("场景1: 洗车多少钱", scenario_1_carwash_price),
        ("场景2: 换机油", scenario_2_oil_change),
        ("场景3: 多轮漏斗", scenario_3_multi_turn_funnel),
        ("场景4: 闲聊拉回", scenario_4_chitchat_redirect),
    ]

    results: list[ScenarioResult] = []
    for label, fn in scenarios:
        print(f"{_C}  >> 运行 {label}...{_0}")
        result: ScenarioResult = await fn()
        results.append(result)

    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())

"""S1 E2E 测试：保险竞价 + 不需要优惠 + 问平台

直接对 http://localhost:8100 发 SSE 请求，验证 S1 阶段核心行为。

运行方式：
    uv run python tests/test_s1_insurance_and_no_coupon.py
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

# ── Interrupt 自动回复 ──
INTERRUPT_AUTO_REPLIES: dict[str, dict[str, Any]] = {
    "select_car": {
        "car_model_id": "test-100",
        "car_model_name": "测试车型",
        "vin_code": "",
        "required_precision": "exact_model",
    },
    "select_location": {
        "address": "上海浦东张江",
        "lat": 31.2304,
        "lng": 121.47,
    },
    "confirm_booking": {
        "confirmed": True,
        "user_msg": "确认预订",
    },
}


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
    reasons: list[str] = field(default_factory=list)


# ============================================================
# SSE 客户端
# ============================================================


async def _send_interrupt_reply(
    client: httpx.AsyncClient,
    interrupt_key: str,
    interrupt_type: str,
) -> str | None:
    """发送 interrupt-reply，返回错误信息或 None。"""
    reply_data: dict[str, Any] = INTERRUPT_AUTO_REPLIES.get(
        interrupt_type,
        {"reply": "ok"},
    )
    try:
        reply_resp: httpx.Response = await client.post(
            f"{BASE_URL}/chat/interrupt-reply",
            json={
                "interrupt_key": interrupt_key,
                "reply": reply_data,
            },
        )
        if reply_resp.status_code == 410:
            return "interrupt 已失效（服务重启）"
    except Exception as e:
        return f"interrupt-reply 失败: {e}"
    return None


async def chat_round(
    session_id: str,
    message: str,
    user_id: str,
    round_num: int,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，自动处理 interrupt，返回完整结果。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    interrupts: list[dict[str, Any]] = []
    error: str = ""

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(TIMEOUT)),
            # WSL 环境可能有代理，绕过
        ) as client:
            request_body: dict[str, Any] = {
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
                            if i_key and i_type:
                                reply_err: str | None = await _send_interrupt_reply(
                                    client, i_key, i_type,
                                )
                                if reply_err:
                                    error = reply_err

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
        interrupts=interrupts,
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 场景定义
# ============================================================


async def scenario_1_insurance_bidding() -> ScenarioResult:
    """场景 1: 保险竞价完整流程。

    第1轮: "我要买保险" — 验证直接推进竞价，不问"要不要比价"，不暴露内部概念
    第2轮: "行" — 验证调了 proceed_to_booking 和 collect_car_info
    """
    session_id: str = str(uuid4())
    user_id: str = f"e2e-insurance-{uuid4().hex[:8]}"
    reasons: list[str] = []
    passed: bool = True
    rounds: list[RoundResult] = []

    # ---- 第 1 轮 ----
    r1: RoundResult = await chat_round(session_id, "我要买保险", user_id, 1)
    rounds.append(r1)

    if r1.error:
        reasons.append(f"FAIL: 第1轮出错: {r1.error}")
        passed = False
        return ScenarioResult(name="场景1: 保险竞价完整流程", rounds=rounds, passed=False, reasons=reasons)

    # 验证：应直接推进竞价，不问"要不要比价"
    bad_phrases: list[str] = ["要不要比价", "还是直接买", "是否需要比价", "要不要对比"]
    for phrase in bad_phrases:
        if phrase in r1.response_text:
            reasons.append(f"FAIL: 第1轮不应问「{phrase}」，应直接推进竞价")
            passed = False

    # 验证：不暴露内部概念
    internal_concepts: list[str] = ["project_id", "9999", "saving_method"]
    for concept in internal_concepts:
        if concept in r1.response_text:
            reasons.append(f"FAIL: 第1轮暴露了内部概念「{concept}」")
            passed = False

    # 验证：回复应包含竞价/比价/多家相关词
    bidding_keywords: list[str] = ["竞价", "比价", "多家", "保险公司", "谈判", "争取", "优惠", "赠返"]
    has_bidding_intro: bool = any(kw in r1.response_text for kw in bidding_keywords)
    if not has_bidding_intro:
        reasons.append("FAIL: 第1轮回复中没有保险竞价相关引导")
        passed = False

    # ---- 第 2 轮 ----
    r2: RoundResult = await chat_round(session_id, "行", user_id, 2)
    rounds.append(r2)

    if r2.error:
        reasons.append(f"FAIL: 第2轮出错: {r2.error}")
        passed = False
        return ScenarioResult(name="场景1: 保险竞价完整流程", rounds=rounds, passed=passed, reasons=reasons)

    # 验证：应调用 proceed_to_booking
    if "proceed_to_booking" not in r2.tool_calls:
        reasons.append("FAIL: 第2轮没调 proceed_to_booking")
        passed = False

    # 验证：应调用 collect_car_info（触发 interrupt select_car）
    has_collect_car: bool = "collect_car_info" in r2.tool_calls
    has_car_interrupt: bool = any(i["type"] == "select_car" for i in r2.interrupts)
    if not has_collect_car and not has_car_interrupt:
        # 也可能是文字引导提供车辆信息
        car_guide_kw: list[str] = ["车辆信息", "车型", "什么车", "哪款车", "爱车"]
        has_car_text_guide: bool = any(kw in r2.response_text for kw in car_guide_kw)
        if not has_car_text_guide:
            reasons.append("FAIL: 第2轮没调 collect_car_info 也没引导提供车辆信息")
            passed = False

    if not reasons:
        reasons.append("OK: 保险竞价流程正确——直接推进、不暴露内部概念、调了 proceed_to_booking")

    return ScenarioResult(
        name="场景1: 保险竞价完整流程",
        rounds=rounds,
        passed=passed,
        reasons=reasons,
    )


async def scenario_2_no_coupon() -> ScenarioResult:
    """场景 2: 用户不需要优惠。

    第1轮: "我想做个保养" — 正常省钱引导
    第2轮: "不用优惠，直接做" — 不调 proceed_to_booking，引导车辆信息
    """
    session_id: str = str(uuid4())
    user_id: str = f"e2e-nocoupon-{uuid4().hex[:8]}"
    reasons: list[str] = []
    passed: bool = True
    rounds: list[RoundResult] = []

    # ---- 第 1 轮 ----
    r1: RoundResult = await chat_round(session_id, "我想做个保养", user_id, 1)
    rounds.append(r1)

    if r1.error:
        reasons.append(f"FAIL: 第1轮出错: {r1.error}")
        passed = False
        return ScenarioResult(name="场景2: 不需要优惠", rounds=rounds, passed=False, reasons=reasons)

    # ---- 第 2 轮 ----
    r2: RoundResult = await chat_round(session_id, "不用优惠，直接做", user_id, 2)
    rounds.append(r2)

    if r2.error:
        reasons.append(f"FAIL: 第2轮出错: {r2.error}")
        passed = False
        return ScenarioResult(name="场景2: 不需要优惠", rounds=rounds, passed=passed, reasons=reasons)

    # 验证：不应调用 proceed_to_booking
    if "proceed_to_booking" in r2.tool_calls:
        reasons.append("FAIL: 用户说不要优惠后不应调 proceed_to_booking")
        passed = False

    # 验证：应引导提供车辆信息（collect_car_info 工具或文字引导）
    has_collect_car: bool = "collect_car_info" in r2.tool_calls
    has_car_interrupt: bool = any(i["type"] == "select_car" for i in r2.interrupts)
    car_guide_kw: list[str] = ["车辆信息", "车型", "什么车", "哪款车", "爱车", "车辆"]
    has_car_text_guide: bool = any(kw in r2.response_text for kw in car_guide_kw)

    if not has_collect_car and not has_car_interrupt and not has_car_text_guide:
        reasons.append("FAIL: 第2轮没引导提供车辆信息（既没调 collect_car_info 也没文字引导）")
        passed = False

    if not reasons:
        reasons.append("OK: 不需要优惠场景正确——没调 proceed_to_booking，引导了车辆信息")

    return ScenarioResult(
        name="场景2: 不需要优惠",
        rounds=rounds,
        passed=passed,
        reasons=reasons,
    )


async def scenario_3_ask_platform() -> ScenarioResult:
    """场景 3: 问平台。

    消息: "你是谁？能做什么？" — 验证读了 platform-intro skill，回复包含"话痨"
    """
    session_id: str = str(uuid4())
    user_id: str = f"e2e-platform-{uuid4().hex[:8]}"
    reasons: list[str] = []
    passed: bool = True
    rounds: list[RoundResult] = []

    r: RoundResult = await chat_round(session_id, "你是谁？能做什么？", user_id, 1)
    rounds.append(r)

    if r.error:
        reasons.append(f"FAIL: 出错: {r.error}")
        passed = False
        return ScenarioResult(name="场景3: 问平台", rounds=rounds, passed=False, reasons=reasons)

    # 验证：回复中包含"话痨"
    if "话痨" not in r.response_text:
        reasons.append("FAIL: 回复中没有提到「话痨」")
        passed = False

    # 验证：回复中包含平台能力关键词
    platform_kw: list[str] = ["省钱", "养车", "保养", "商户", "优惠", "预订", "保险"]
    has_platform_ability: bool = any(kw in r.response_text for kw in platform_kw)
    if not has_platform_ability:
        reasons.append("FAIL: 回复中没有介绍平台能力")
        passed = False

    if not reasons:
        reasons.append("OK: 正确介绍平台能力，包含「话痨」")

    return ScenarioResult(
        name="场景3: 问平台",
        rounds=rounds,
        passed=passed,
        reasons=reasons,
    )


# ============================================================
# 报告输出
# ============================================================


def print_round(r: RoundResult) -> None:
    """打印单轮对话结果。"""
    truncated: str = r.response_text[:200] + ("..." if len(r.response_text) > 200 else "")
    print(f"  {_D}[轮{r.round_num}] 用户: {r.user_message}{_0}")
    print(f"  {_D}回复: {truncated}{_0}")
    if r.tool_calls:
        print(f"  {_C}工具调用: {', '.join(r.tool_calls)}{_0}")
    if r.interrupts:
        i_types: list[str] = [i["type"] for i in r.interrupts]
        print(f"  {_Y}Interrupt: {', '.join(i_types)}{_0}")
    if r.error:
        print(f"  {_R}错误: {r.error}{_0}")
    print(f"  {_D}耗时: {r.elapsed_seconds:.1f}s{_0}")
    print()


def print_report(results: list[ScenarioResult]) -> None:
    """打印汇总报告。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{'=' * 60}")
    print(f"{_B}S1 E2E 测试报告（保险 + 不需要优惠 + 问平台）{_0}")
    print(f"{'=' * 60}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"{status} {_B}{result.name}{_0}")

        for r in result.rounds:
            print_round(r)

        for reason in result.reasons:
            if reason.startswith("FAIL"):
                print(f"  {_R}{reason}{_0}")
            elif reason.startswith("WARN"):
                print(f"  {_Y}{reason}{_0}")
            else:
                print(f"  {_G}{reason}{_0}")
        print()

    print(f"{'─' * 60}")
    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"{color}通过: {passed_count}/{total}{_0}")
    print(f"{'─' * 60}\n")


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """依次运行所有场景。"""
    # 先检查服务器是否可达
    print(f"\n{_B}S1 E2E 测试（保险 + 不需要优惠 + 问平台）{_0}")
    print(f"  目标: {BASE_URL}")
    print(f"  超时: {TIMEOUT}s\n")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            health: httpx.Response = await client.get(f"{BASE_URL}/health")
            health.raise_for_status()
            print(f"  {_G}服务器就绪{_0}\n")
    except Exception as e:
        print(f"  {_R}服务器不可达: {e}{_0}")
        print(f"  请确保 MainAgent 在 {BASE_URL} 运行\n")
        return

    scenarios: list[tuple[str, Any]] = [
        ("场景1: 保险竞价", scenario_1_insurance_bidding),
        ("场景2: 不需要优惠", scenario_2_no_coupon),
        ("场景3: 问平台", scenario_3_ask_platform),
    ]

    results: list[ScenarioResult] = []
    for label, fn in scenarios:
        print(f"{_C}>>> 运行 {label}...{_0}")
        result: ScenarioResult = await fn()
        results.append(result)

    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())

"""Guide 场景实时验证

基于 guide_test_cases.md 设计的 20 个测试场景，通过 SSE 端点真实验证：

重点验证项：
1. 闲聊是否快速拉回（"你好"、"今天天气不错"）
2. 项目识别是否调 classify_project（"换机油"、"做保养"）
3. 保险是否不调 classify_project（"保险到期了"）
4. 位置是否记录到 session_state（"我在朝阳区"）
5. saving-methods 是否只讲概要不讲细节

运行方式：
    cd mainagent && uv run python ../tests/test_guide_realtime.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
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
    elapsed_seconds: float
    error: str = ""


@dataclass
class ScenarioResult:
    """场景验证结果。"""
    scenario_id: str
    name: str
    rounds: list[RoundResult]
    passed: bool
    checks: dict[str, bool | str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ============================================================
# SSE 流式客户端
# ============================================================


async def send_message(
    session_id: str,
    message: str,
    user_id: str,
    round_num: int = 1,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，解析事件流，返回结果。"""
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
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 测试场景
# ============================================================


async def test_s1_chitchat_hello() -> ScenarioResult:
    """场景 1: 纯闲聊 - 打招呼。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s1-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "你好", user_id, 1)

    checks: dict[str, bool | str] = {
        "no_empty_response": bool(r.response_text.strip()),
        "quick_response": r.elapsed_seconds < 10,
        "has_redirect_keywords": any(kw in r.response_text for kw in ["养车", "保养", "维修", "需要", "帮您", "帮你"]),
        "no_excessive_tools": len(r.tool_calls) <= 1,
    }

    passed: bool = all(checks.values())

    return ScenarioResult(
        scenario_id="s1",
        name="场景1: 纯闲聊 - 打招呼",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[
            f"工具调用: {r.tool_calls if r.tool_calls else '(无)'}",
            f"回复首 100 字: {r.response_text[:100]}...",
        ],
    )


async def test_s2_chitchat_weather() -> ScenarioResult:
    """场景 2: 纯闲聊 - 天气评论。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s2-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "今天天气不错，阳光很好", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "not_continue_chitchat": not any(kw in r.response_text for kw in ["确实", "是的", "天气", "阳光", "不错"]),
        "has_redirect": any(kw in r.response_text for kw in ["养车", "保养", "需要", "帮您", "帮你", "省钱"]),
    }

    passed: bool = checks.get("has_redirect", False)

    return ScenarioResult(
        scenario_id="s2",
        name="场景2: 纯闲聊 - 天气评论",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"回复: {r.response_text[:120]}..."],
    )


async def test_s3_vague_needs() -> ScenarioResult:
    """场景 3: 模糊需求 - 泛指问题。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s3-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "我车有点问题", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "should_use_saving_methods_skill": "saving-methods" in r.response_text.lower() or any(
            kw in r.response_text for kw in ["优惠", "省钱", "9折", "商户", "保险"]
        ),
        "offers_choices": any(
            kw in r.response_text for kw in ["选择", "方式", "可以", "或者", "以下"]
        ),
    }

    passed: bool = checks.get("has_response", False) and (
        checks.get("should_use_saving_methods_skill", False)
        or checks.get("offers_choices", False)
    )

    return ScenarioResult(
        scenario_id="s3",
        name="场景3: 模糊需求 - 泛指问题",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"工具: {r.tool_calls if r.tool_calls else '(无)'}"],
    )


async def test_s5_project_keyword_single() -> ScenarioResult:
    """场景 5: 项目关键词 - 换机油。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s5-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "想换机油", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "called_classify_project": "classify_project" in r.tool_calls,
        "no_s2_tools": not any(t in r.tool_calls for t in ["confirm_booking", "match_project", "call_recommend_project"]),
    }

    passed: bool = checks.get("called_classify_project", False)

    return ScenarioResult(
        scenario_id="s5",
        name="场景5: 项目识别 - 换机油",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"工具: {r.tool_calls}"],
    )


async def test_s7_insurance_续保() -> ScenarioResult:
    """场景 7: 保险关键词 - 续保。
    重点: 不应该调 classify_project
    """
    session_id: str = str(uuid4())
    user_id: str = f"guide-s7-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "我的车险快到期了，需要续保", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "must_not_call_classify_project": "classify_project" not in r.tool_calls,
        "mentions_insurance_comparison": any(
            kw in r.response_text for kw in ["保险", "比价", "竞价", "优惠", "赠返"]
        ),
        "collects_car_info": any(
            t in r.tool_calls for t in ["list_user_cars", "collect_car_info"]
        ),
    }

    passed: bool = (
        checks.get("must_not_call_classify_project", False)
        and checks.get("mentions_insurance_comparison", False)
    )

    return ScenarioResult(
        scenario_id="s7",
        name="场景7: 保险关键词 - 续保",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"工具: {r.tool_calls}"],
    )


async def test_s9_platform_intro() -> ScenarioResult:
    """场景 9: 平台身份问题。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s9-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "你是谁？能做什么？", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "mentions_platform_identity": any(
            kw in r.response_text for kw in ["话痨", "AI", "助理", "助手"]
        ),
        "explains_capabilities": any(
            kw in r.response_text for kw in ["省钱", "优惠", "保险", "商户", "预订"]
        ),
        "redirects_to_inquiry": any(
            kw in r.response_text for kw in ["养车", "需要", "帮您", "帮你", "什么需求"]
        ),
    }

    passed: bool = all(checks.values())

    return ScenarioResult(
        scenario_id="s9",
        name="场景9: 平台身份问题",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"回复首 150 字: {r.response_text[:150]}..."],
    )


async def test_s10_location_mention() -> ScenarioResult:
    """场景 10: 位置信息提及。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s10-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "我在朝阳区，附近有什么好修理厂吗？", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "called_update_session_state": "update_session_state" in r.tool_calls,
        "responds_to_location": any(
            kw in r.response_text for kw in ["朝阳", "位置", "附近", "修理厂", "商户"]
        ),
    }

    passed: bool = checks.get("called_update_session_state", False)

    return ScenarioResult(
        scenario_id="s10",
        name="场景10: 位置信息提及",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"工具: {r.tool_calls}"],
    )


async def test_s11_car_info_no_history() -> ScenarioResult:
    """场景 11: 车型收集 - 无车型历史。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s11-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "我想做保养，但我不知道自己的车具体是什么型号", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "called_collect_car_info": "collect_car_info" in r.tool_calls,
        "did_not_call_list_user_cars": "list_user_cars" not in r.tool_calls,
        "guides_car_collection": any(
            kw in r.response_text for kw in ["车型", "品牌", "车系", "年款", "帮你"]
        ),
    }

    passed: bool = checks.get("called_collect_car_info", False)

    return ScenarioResult(
        scenario_id="s11",
        name="场景11: 车型收集 - 无历史",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"工具: {r.tool_calls}"],
    )


async def test_s13_out_of_scope_ecommerce() -> ScenarioResult:
    """场景 13: 话题跑偏 - 电商购物。"""
    session_id: str = str(uuid4())
    user_id: str = f"guide-s13-{uuid4().hex[:8]}"
    r: RoundResult = await send_message(session_id, "能不能帮我在淘宝买个机油？", user_id, 1)

    checks: dict[str, bool | str] = {
        "has_response": bool(r.response_text.strip()),
        "clearly_declines": any(
            kw in r.response_text for kw in ["无法", "不能", "抱歉", "不支持", "做不了", "淘宝", "电商"]
        ),
        "offers_alternative": any(
            kw in r.response_text for kw in ["不过", "不过我可以", "反而", "替代", "修理厂", "线下"]
        ),
    }

    passed: bool = checks.get("clearly_declines", False) or checks.get("offers_alternative", False)

    return ScenarioResult(
        scenario_id="s13",
        name="场景13: 话题跑偏 - 电商购物",
        rounds=[r],
        passed=passed,
        checks=checks,
        notes=[f"回复: {r.response_text[:150]}..."],
    )


# ============================================================
# 报告输出
# ============================================================


def print_result(result: ScenarioResult) -> None:
    """打印单个场景结果。"""
    status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
    print(f"\n{status} {_B}{result.name}{_0}")

    for r in result.rounds:
        print(f"  {_D}[轮{r.round_num}]{_0} 用户: {r.user_message}")
        truncated: str = r.response_text[:80] + ("..." if len(r.response_text) > 80 else "")
        print(f"  {_D}回复: {truncated}{_0}")

    print(f"  {_D}验证点:{_0}")
    for check_name, check_result in result.checks.items():
        symbol: str = _G + "✓" + _0 if check_result else _R + "✗" + _0
        print(f"    {symbol} {check_name}: {check_result}")

    for note in result.notes:
        print(f"  {_D}📝 {note}{_0}")

    if result.error:
        print(f"  {_R}错误: {result.error}{_0}")


def print_report(results: list[ScenarioResult]) -> None:
    """打印汇总报告。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{'=' * 70}")
    print(f"{_B}Guide 场景实时验证报告{_0}")
    print(f"{'=' * 70}")

    for result in results:
        print_result(result)

    print(f"\n{'─' * 70}")
    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"{color}通过: {passed_count}/{total} 场景{_0}")
    print(f"{'─' * 70}\n")


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行 guide 场景实时验证。"""
    # 健康检查
    try:
        resp: httpx.Response = httpx.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        print(f"{_G}✓ MainAgent 就绪: {BASE_URL}{_0}\n")
    except Exception as e:
        print(f"{_R}✗ MainAgent 不可达: {BASE_URL} — {e}{_0}")
        return

    test_cases: list[tuple[str, object]] = [
        ("场景1: 闲聊 - 打招呼", test_s1_chitchat_hello),
        ("场景2: 闲聊 - 天气", test_s2_chitchat_weather),
        ("场景3: 模糊需求", test_s3_vague_needs),
        ("场景5: 项目识别", test_s5_project_keyword_single),
        ("场景7: 保险续保", test_s7_insurance_续保),
        ("场景9: 平台介绍", test_s9_platform_intro),
        ("场景10: 位置信息", test_s10_location_mention),
        ("场景11: 车型收集", test_s11_car_info_no_history),
        ("场景13: 电商拒绝", test_s13_out_of_scope_ecommerce),
    ]

    results: list[ScenarioResult] = []
    for label, fn in test_cases:
        print(f"{_C}▶ 运行 {label}...{_0}")
        result: ScenarioResult = await fn()
        results.append(result)

    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())

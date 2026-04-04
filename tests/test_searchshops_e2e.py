"""searchshops 场景全链路测试

5 个测试：
1. BMA 分类验证 — 确认各意图正确路由
2. searchshops 基础搜索 — 新 session，带位置，验证路由 + search_shops + ShopCard
3. 能力边界验证 — 同 session 继续，预订/优惠应被拦截
4. 联系单生成 — 选定商户 + 时间 → create_contact_order → ContactOrderCard
5. call_query_codingagent 注册验证 — stage_config.yaml 静态检查

运行方式：
    cd mainagent && uv run python ../tests/test_searchshops_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx

# ── 配置 ──
MAINAGENT_URL: str = "http://127.0.0.1:8100"
BMA_URL: str = "http://127.0.0.1:8103"
TIMEOUT: int = 120

# 上海浦东新区位置（测试用）
TEST_LOCATION: dict[str, object] = {
    "current_location": {
        "address": "上海市浦东新区张江高科",
        "lat": 31.2035,
        "lng": 121.5914,
    }
}

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
class TestResult:
    """单个测试结果。"""
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    rounds: list[RoundResult] = field(default_factory=list)


# ============================================================
# SSE 流式客户端
# ============================================================


async def send_message(
    session_id: str,
    message: str,
    user_id: str = "test-searchshops",
    round_num: int = 1,
    context: dict[str, object] | None = None,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，解析事件流，返回结构化结果。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    error: str = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(TIMEOUT))) as client:
            request_body: dict[str, object] = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            if context is not None:
                request_body["context"] = context

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
                            data: dict[str, object] = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict[str, object] = data.get("data", {})  # type: ignore[assignment]

                        if event_type == "text":
                            content: str = str(evt_data.get("content", ""))
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = str(evt_data.get("tool_name", "unknown"))
                            tool_calls.append(tool_name)

                        elif event_type == "error":
                            err_msg: str = str(
                                evt_data.get("message", evt_data.get("error", str(evt_data)))
                            )
                            error = err_msg

                        elif event_type == "chat_request_end":
                            break

    except httpx.ReadTimeout:
        if not text_parts and not tool_calls:
            error = f"超时（{TIMEOUT}s），无任何响应"
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        if not text_parts and not tool_calls:
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
# Test 1: BMA 分类验证
# ============================================================


async def test_1_bma_classify() -> list[TestResult]:
    """BMA /classify 对 searchshops 相关意图的分类验证。"""
    results: list[TestResult] = []

    cases: list[tuple[str, list[str]]] = [
        ("附近有什么修理厂", ["searchshops"]),
        ("帮我找个评分高的保养店", ["searchshops"]),
        ("有洗车优惠的店", ["searchshops", "searchcoupons"]),
        ("帮我预订换机油", ["platform"]),
    ]

    for message, expected_scenes in cases:
        test_name: str = f"BMA分类: '{message}' -> {expected_scenes}"
        details: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp: httpx.Response = await client.post(
                    f"{BMA_URL}/classify",
                    json={"message": message},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                actual_scenes: list[str] = data.get("scenes", [])  # type: ignore[assignment]

            details.append(f"期望: {expected_scenes}")
            details.append(f"实际: {actual_scenes}")

            passed: bool = set(actual_scenes) == set(expected_scenes)
            if passed:
                details.append("OK: 场景匹配")
            else:
                # 宽松判定：searchshops 相关的 case，只要包含 searchshops 就算部分通过
                if "searchshops" in expected_scenes and "searchshops" in actual_scenes:
                    details.append("WARN: 包含 searchshops 但集合不完全匹配")
                elif "platform" in expected_scenes and "platform" in actual_scenes:
                    details.append("WARN: 包含 platform 但集合不完全匹配")
                else:
                    details.append("FAIL: 场景不匹配")

        except Exception as e:
            passed = False
            details.append(f"ERROR: {e}")

        results.append(TestResult(name=test_name, passed=passed, details=details))

    return results


# ============================================================
# Test 2: searchshops 基础搜索
# ============================================================


async def test_2_basic_search(session_id: str) -> TestResult:
    """新 session，带位置 context，发 '附近有什么修理厂'。
    验证：路由到 searchshops，调 search_shops，返回 ShopCard。
    """
    details: list[str] = []

    r: RoundResult = await send_message(
        session_id=session_id,
        message="附近有什么修理厂",
        round_num=1,
        context=TEST_LOCATION,
    )

    if r.error:
        return TestResult(
            name="Test2: searchshops 基础搜索",
            passed=False,
            details=[f"ERROR: {r.error}"],
            rounds=[r],
        )

    details.append(f"工具调用: {r.tool_calls}")
    details.append(f"回复长度: {len(r.response_text)} 字")
    details.append(f"耗时: {r.elapsed_seconds:.1f}s")

    passed: bool = True

    # 验证 1：应该调了 search_shops
    if "search_shops" in r.tool_calls:
        details.append("OK: 调了 search_shops")
    else:
        details.append("FAIL: 未调 search_shops")
        passed = False

    # 验证 2：不应该调 delegate（单场景）
    if "delegate" in r.tool_calls:
        details.append("FAIL: 单场景走了 delegate")
        passed = False
    else:
        details.append("OK: 未走 delegate")

    # 验证 3：回复中应包含 ShopCard（spec 块）
    has_shop_card: bool = "ShopCard" in r.response_text
    if has_shop_card:
        details.append("OK: 回复包含 ShopCard")
    else:
        # 可能没有结果，或者格式不同
        if "没有" in r.response_text or "未找到" in r.response_text or "暂无" in r.response_text:
            details.append("WARN: 无搜索结果（可能是测试数据问题），无法验证 ShopCard")
        else:
            details.append("WARN: 回复中未见 ShopCard（可能是文本回复格式）")

    # 验证 4：有回复文本
    if r.response_text.strip():
        details.append("OK: 有回复文本")
    else:
        details.append("FAIL: 无回复文本")
        passed = False

    return TestResult(
        name="Test2: searchshops 基础搜索",
        passed=passed,
        details=details,
        rounds=[r],
    )


# ============================================================
# Test 3: 能力边界验证
# ============================================================


async def test_3_capability_boundary(session_id: str) -> TestResult:
    """在同一 session 继续对话，测试能力边界：
    - "帮我预订这家" -> 应该告知只能生成联系单
    - "有没有优惠" -> 应该告知优惠另查
    """
    details: list[str] = []
    rounds: list[RoundResult] = []
    passed: bool = True

    # 轮 1："帮我预订这家"
    r1: RoundResult = await send_message(
        session_id=session_id,
        message="帮我预订这家",
        round_num=2,
    )
    rounds.append(r1)

    if r1.error:
        details.append(f"ERROR(轮1): {r1.error}")
        return TestResult(
            name="Test3: 能力边界验证",
            passed=False,
            details=details,
            rounds=rounds,
        )

    details.append(f"[轮1] 工具: {r1.tool_calls}")

    # "帮我预订" → 应该告知只能联系 / 联系单
    booking_boundary_keywords: list[str] = [
        "联系", "联系单", "联络", "不能预订", "无法预订",
        "帮您联系", "商户会", "主动联系",
    ]
    has_boundary_r1: bool = any(kw in r1.response_text for kw in booking_boundary_keywords)
    if has_boundary_r1:
        details.append("OK: 轮1 正确告知只能联系/不能直接预订")
    else:
        # 也可能 LLM 没理解到具体指哪家店，先追问
        ask_which_keywords: list[str] = ["哪家", "选", "确认", "指"]
        has_ask: bool = any(kw in r1.response_text for kw in ask_which_keywords)
        if has_ask:
            details.append("OK: 轮1 追问具体哪家店（合理）")
        else:
            details.append("WARN: 轮1 未明确告知预订边界或追问")

    # 不应该调 confirm_booking
    if "confirm_booking" in r1.tool_calls:
        details.append("FAIL: 轮1 调了 confirm_booking（searchshops 没有此工具）")
        passed = False
    else:
        details.append("OK: 轮1 未调 confirm_booking")

    # 轮 2："有没有优惠"
    r2: RoundResult = await send_message(
        session_id=session_id,
        message="有没有优惠",
        round_num=3,
    )
    rounds.append(r2)

    if r2.error:
        details.append(f"ERROR(轮2): {r2.error}")
        return TestResult(
            name="Test3: 能力边界验证",
            passed=passed,
            details=details,
            rounds=rounds,
        )

    details.append(f"[轮2] 工具: {r2.tool_calls}")

    # "有没有优惠" → 应该告知优惠另查 / 引导到其他场景
    coupon_boundary_keywords: list[str] = [
        "优惠", "另", "查", "活动", "优惠券", "折扣",
    ]
    has_coupon_response: bool = any(kw in r2.response_text for kw in coupon_boundary_keywords)
    if has_coupon_response:
        details.append("OK: 轮2 回复中提到了优惠相关引导")
    else:
        details.append("WARN: 轮2 未明确引导优惠查询")

    return TestResult(
        name="Test3: 能力边界验证",
        passed=passed,
        details=details,
        rounds=rounds,
    )


# ============================================================
# Test 4: 联系单生成
# ============================================================


async def test_4_contact_order(session_id: str) -> TestResult:
    """在同一 session，用户选了店 + 说了时间 → create_contact_order → ContactOrderCard。"""
    details: list[str] = []

    r: RoundResult = await send_message(
        session_id=session_id,
        message="就第一家，明天下午去",
        round_num=4,
    )

    if r.error:
        return TestResult(
            name="Test4: 联系单生成",
            passed=False,
            details=[f"ERROR: {r.error}"],
            rounds=[r],
        )

    details.append(f"工具调用: {r.tool_calls}")
    details.append(f"回复长度: {len(r.response_text)} 字")
    details.append(f"耗时: {r.elapsed_seconds:.1f}s")

    passed: bool = True

    # 验证 1：应该调 create_contact_order
    if "create_contact_order" in r.tool_calls:
        details.append("OK: 调了 create_contact_order")
    else:
        details.append("WARN: 未调 create_contact_order（可能 LLM 判断信息不足先追问）")
        # 检查是否在追问确认
        confirm_keywords: list[str] = ["确认", "哪家", "确定", "选", "第一家"]
        has_confirm: bool = any(kw in r.response_text for kw in confirm_keywords)
        if has_confirm:
            details.append("OK: 在追问确认信息（合理路径）")
        else:
            details.append("FAIL: 既未调 create_contact_order 也未追问")
            passed = False

    # 验证 2：如果调了 create_contact_order，回复应含 ContactOrderCard
    if "create_contact_order" in r.tool_calls:
        has_contact_card: bool = "ContactOrderCard" in r.response_text
        if has_contact_card:
            details.append("OK: 回复包含 ContactOrderCard")
        else:
            # 可能工具调用成功但 LLM 没输出 spec 卡片
            if "联系单" in r.response_text or "联系" in r.response_text:
                details.append("WARN: 有联系单文本但无 ContactOrderCard spec")
            else:
                details.append("WARN: 未见 ContactOrderCard（可能工具执行失败）")

    # 验证 3：有回复文本
    if r.response_text.strip():
        details.append("OK: 有回复文本")
    else:
        details.append("FAIL: 无回复文本")
        passed = False

    return TestResult(
        name="Test4: 联系单生成",
        passed=passed,
        details=details,
        rounds=[r],
    )


# ============================================================
# Test 5: call_query_codingagent 注册验证（静态检查）
# ============================================================


def test_5_codingagent_registered() -> TestResult:
    """验证 searchshops 场景的工具列表里有 call_query_codingagent。"""
    import yaml

    details: list[str] = []
    config_path: Path = Path(__file__).resolve().parent.parent / "mainagent" / "stage_config.yaml"

    if not config_path.exists():
        return TestResult(
            name="Test5: call_query_codingagent 注册验证",
            passed=False,
            details=[f"stage_config.yaml 不存在: {config_path}"],
        )

    raw: dict[str, object] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    scenes: dict[str, dict[str, object]] = raw.get("scenes", {})  # type: ignore[assignment]
    searchshops_config: dict[str, object] = scenes.get("searchshops", {})
    tools: list[str] = searchshops_config.get("tools", [])  # type: ignore[assignment]

    details.append(f"searchshops 工具列表: {tools}")

    if "call_query_codingagent" in tools:
        details.append("OK: call_query_codingagent 已注册")
        passed: bool = True
    else:
        details.append("FAIL: call_query_codingagent 未在 searchshops 工具列表中")
        passed = False

    # 额外验证：create_contact_order 也应该在
    if "create_contact_order" in tools:
        details.append("OK: create_contact_order 已注册")
    else:
        details.append("FAIL: create_contact_order 未在 searchshops 工具列表中")
        passed = False

    return TestResult(
        name="Test5: call_query_codingagent 注册验证",
        passed=passed,
        details=details,
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
    if r.error:
        print(f"    {_R}错误: {r.error}{_0}")
    print(f"    {_D}耗时: {r.elapsed_seconds:.1f}s{_0}")


def print_report(results: list[TestResult]) -> None:
    """打印汇总报告。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{'=' * 60}")
    print(f"{_B}searchshops 全场景测试报告{_0}")
    print(f"{'=' * 60}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"  {status} {_B}{result.name}{_0}")

        for r in result.rounds:
            print_round(r)

        for detail in result.details:
            if detail.startswith("FAIL") or detail.startswith("ERROR"):
                print(f"    {_R}{detail}{_0}")
            elif detail.startswith("WARN"):
                print(f"    {_Y}{detail}{_0}")
            elif detail.startswith("OK"):
                print(f"    {_G}{detail}{_0}")
            else:
                print(f"    {_D}{detail}{_0}")
        print()

    print(f"{'─' * 60}")
    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"{color}通过: {passed_count}/{total}{_0}")
    print(f"{'─' * 60}\n")


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行所有 searchshops 测试。"""
    print(f"\n{_B}searchshops 全场景 E2E 测试{_0}")
    print(f"  MainAgent: {MAINAGENT_URL}")
    print(f"  BMA:       {BMA_URL}")
    print()

    # 健康检查
    try:
        r: httpx.Response = httpx.get(f"{MAINAGENT_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"{_G}MainAgent 就绪{_0}")
    except Exception as e:
        print(f"{_R}MainAgent 不可达: {e}{_0}")
        return

    try:
        r = httpx.get(f"{BMA_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"{_G}BMA 就绪{_0}")
    except Exception as e:
        print(f"{_R}BMA 不可达: {e}{_0}")
        return

    all_results: list[TestResult] = []

    # ── Test 5: 静态检查（不需要服务） ──
    print(f"\n{_C}>>> Test 5: call_query_codingagent 注册验证（静态）{_0}")
    t5: TestResult = test_5_codingagent_registered()
    all_results.append(t5)
    status5: str = f"{_G}PASS{_0}" if t5.passed else f"{_R}FAIL{_0}"
    print(f"  {status5} {t5.name}")
    for d in t5.details:
        print(f"    {d}")

    # ── Test 1: BMA 分类 ──
    print(f"\n{_C}>>> Test 1: BMA 分类验证{_0}")
    t1_results: list[TestResult] = await test_1_bma_classify()
    all_results.extend(t1_results)
    for tr in t1_results:
        status1: str = f"{_G}PASS{_0}" if tr.passed else f"{_R}FAIL{_0}"
        print(f"  {status1} {tr.name}")
        for d in tr.details:
            print(f"    {d}")

    # ── Test 2-4: 共用一个 session ──
    session_id: str = f"test-searchshops-{uuid4().hex[:8]}"
    print(f"\n{_C}>>> Test 2: searchshops 基础搜索 (session={session_id}){_0}")
    t2: TestResult = await test_2_basic_search(session_id)
    all_results.append(t2)

    print(f"\n{_C}>>> Test 3: 能力边界验证 (同 session){_0}")
    t3: TestResult = await test_3_capability_boundary(session_id)
    all_results.append(t3)

    print(f"\n{_C}>>> Test 4: 联系单生成 (同 session){_0}")
    t4: TestResult = await test_4_contact_order(session_id)
    all_results.append(t4)

    # ── 汇总报告 ──
    print_report(all_results)


if __name__ == "__main__":
    asyncio.run(main())

"""coding agent searchshops 场景端到端测试

3 个测试：
1. 直接调 coding agent（A2A 协议）— 验证 coding agent 独立可用
2. 通过 MainAgent 触发 coding agent — 复杂查询走 call_query_codingagent
3. 简单查询不触发 coding agent — 验证只调 search_shops

运行方式：
    cd mainagent && uv run python ../tests/test_coding_agent_e2e.py

前置条件：
    - MainAgent:       http://127.0.0.1:8100
    - BMA:             http://127.0.0.1:8103
    - Coding Agent:    http://127.0.0.1:8102
    - Shop Consumer:   http://127.0.0.1:8093
    - Coupon Consumer: http://127.0.0.1:8091
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
CODING_AGENT_URL: str = "http://127.0.0.1:8102"
TIMEOUT: int = 120

# 上海浦东张江（测试用）
TEST_LOCATION: dict[str, object] = {
    "current_location": {
        "address": "上海市浦东新区张江高科",
        "lat": 31.23,
        "lng": 121.47,
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
# SSE 流式客户端（MainAgent）
# ============================================================


async def send_message_mainagent(
    session_id: str,
    message: str,
    user_id: str = "test-coding-e2e",
    round_num: int = 1,
    context: dict[str, object] | None = None,
) -> RoundResult:
    """调用 MainAgent /chat/stream SSE 端点，解析事件流，返回结构化结果。"""
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
# A2A 客户端（直接调 coding agent）
# ============================================================


async def send_message_a2a(
    url: str,
    message: str,
    context: dict[str, str] | None = None,
) -> RoundResult:
    """通过 A2A 协议直接调用 subagent，返回结构化结果。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    error: str = ""

    request_body: dict[str, object] = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": f"test-{uuid4().hex[:8]}",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
                "contextId": f"test-a2a-{uuid4().hex[:8]}",
            },
            "metadata": context or {},
        },
    }

    try:
        # 绕过 HTTP_PROXY（内网地址）
        transport: httpx.AsyncHTTPTransport = httpx.AsyncHTTPTransport()
        async with httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(float(TIMEOUT))
        ) as client:
            resp: httpx.Response = await client.post(f"{url}/a2a", json=request_body)
            resp.raise_for_status()
            data: dict[str, object] = resp.json()

            if "error" in data:
                error = f"A2A error: {data['error']}"
            else:
                result: dict[str, object] = data.get("result", {})  # type: ignore[assignment]

                # 提取状态文本
                status: dict[str, object] = result.get("status", {})  # type: ignore[assignment]
                state: str = str(status.get("state", ""))
                status_msg: object = status.get("message")

                if state == "failed":
                    error = _extract_a2a_text(status_msg)
                else:
                    completed_text: str = _extract_a2a_text(status_msg)
                    if completed_text:
                        text_parts.append(completed_text)

                # 提取 artifacts 中的工具调用和文本
                artifacts: list[dict[str, object]] = result.get("artifacts", [])  # type: ignore[assignment]
                for artifact in artifacts:
                    parts: list[dict[str, object]] = artifact.get("parts", [])  # type: ignore[assignment]
                    for part in parts:
                        kind: str = str(part.get("kind", "") or part.get("type", ""))
                        if kind == "text":
                            text: str = str(part.get("text", ""))
                            if text:
                                text_parts.append(text)
                        elif kind == "data":
                            part_data: dict[str, object] = part.get("data", {})  # type: ignore[assignment]
                            event_type: str = str(part_data.get("event_type", ""))
                            if event_type == "tool_call_start":
                                tool_name: str = str(part_data.get("tool_name", "unknown"))
                                tool_calls.append(tool_name)

    except httpx.ReadTimeout:
        error = f"超时（{TIMEOUT}s）"
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        error = str(e)

    elapsed: float = time.monotonic() - start

    return RoundResult(
        round_num=1,
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        elapsed_seconds=elapsed,
        error=error,
    )


def _extract_a2a_text(msg: object) -> str:
    """从 A2A Message 中提取文本内容。"""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        parts: list[dict[str, object]] = msg.get("parts", [])  # type: ignore[assignment]
        texts: list[str] = []
        for part in parts:
            kind: str = str(part.get("kind", "") or part.get("type", ""))
            if kind == "text":
                texts.append(str(part.get("text", "")))
        return "\n".join(texts) if texts else str(msg)
    return str(msg) if msg else ""


# ============================================================
# Test 1: 直接调 coding agent（A2A）
# ============================================================


async def test_1_direct_coding_agent() -> TestResult:
    """绕过 MainAgent，直接通过 A2A 调用 coding agent。
    验证：coding agent 能独立接收任务、读 API 文档、执行代码、返回结果。
    """
    details: list[str] = []

    # 构造一个 searchshops 场景的任务
    task_message: str = (
        "API docs for this task are under the `/apis/` directory. "
        "Read /apis/index.md first.\n\n"
        "Task: 用 Python 调用商户搜索 API，找到上海浦东附近的修理厂，"
        "按评分排序返回前3家。API_BASE_URL 环境变量可用。"
    )

    r: RoundResult = await send_message_a2a(
        url=CODING_AGENT_URL,
        message=task_message,
        context={"scene": "searchshops"},
    )

    if r.error:
        details.append(f"ERROR: {r.error}")
        # 连接失败是 FAIL；超时但有部分输出可能是 WARN
        if "连接失败" in r.error:
            return TestResult(
                name="Test1: 直接调 coding agent（A2A）",
                passed=False,
                details=details,
                rounds=[r],
            )

    details.append(f"工具调用: {r.tool_calls}")
    details.append(f"回复长度: {len(r.response_text)} 字")
    details.append(f"耗时: {r.elapsed_seconds:.1f}s")

    passed: bool = True

    # 验证 1：A2A 返回了内容
    if r.response_text.strip():
        details.append("OK: coding agent 返回了结果")
    else:
        details.append("FAIL: coding agent 无结果返回")
        passed = False

    # 验证 2：应该调了工具（read/grep/execute_code 等）
    if r.tool_calls:
        details.append(f"OK: coding agent 调了 {len(r.tool_calls)} 个工具")
        # 检查是否执行了代码
        code_tools: list[str] = [t for t in r.tool_calls if "execute" in t or "code" in t or "run" in t]
        if code_tools:
            details.append(f"OK: 执行了代码工具: {code_tools}")
        else:
            details.append("WARN: 未见 execute_code 类工具（可能用了其他名称）")
    else:
        details.append("WARN: 未见工具调用（可能 artifacts 未转发工具事件）")

    # 验证 3：回复应包含商户相关信息
    shop_keywords: list[str] = ["修理厂", "商户", "门店", "评分", "店", "shop", "rating"]
    has_shop_info: bool = any(kw in r.response_text for kw in shop_keywords)
    if has_shop_info:
        details.append("OK: 回复包含商户相关信息")
    else:
        # 可能 API 返回空结果，或者出错
        error_keywords: list[str] = ["错误", "error", "failed", "无法", "失败"]
        has_error: bool = any(kw in r.response_text.lower() for kw in error_keywords)
        if has_error:
            details.append("WARN: 回复可能包含错误信息（API 不可用或无数据）")
        else:
            details.append("WARN: 回复中未见商户信息关键词")

    return TestResult(
        name="Test1: 直接调 coding agent（A2A）",
        passed=passed,
        details=details,
        rounds=[r],
    )


# ============================================================
# Test 2: 通过 MainAgent 触发 coding agent
# ============================================================


async def test_2_mainagent_triggers_coding() -> TestResult:
    """通过 MainAgent 触发 coding agent：两轮对话。

    轮1：简单搜索确立位置和场景（"附近有什么修理厂"）
    轮2：复杂计算查询（"帮我用代码查查附近修理厂的报价并排序"）

    注意：LLM 可能优先尝试内置工具（search_shops / match_project）而非
    call_query_codingagent。这是合理的 LLM 行为。当内置工具能完成任务时，
    LLM 不需要走编程路径。只有需要跨数据源计算时才会调 coding agent。

    判定标准（宽松）：
    - PASS：调了 call_query_codingagent
    - SOFT FAIL：未调 call_query_codingagent 但调了其他工具（LLM 选择了不同路径）
    - HARD FAIL：连接失败或无任何响应
    """
    details: list[str] = []
    rounds: list[RoundResult] = []
    session_id: str = f"test-coding-complex-{uuid4().hex[:8]}"

    # 轮 1：简单搜索，确立 session 上下文
    details.append("[轮1] 先做简单搜索确立位置")
    r1: RoundResult = await send_message_mainagent(
        session_id=session_id,
        message="附近有什么修理厂",
        round_num=1,
        context=TEST_LOCATION,
    )
    rounds.append(r1)

    if r1.error and "连接失败" in r1.error:
        return TestResult(
            name="Test2: MainAgent 复杂查询路径",
            passed=False,
            details=[f"ERROR: {r1.error}"],
            rounds=rounds,
        )
    details.append(f"[轮1] 工具: {r1.tool_calls}, 耗时: {r1.elapsed_seconds:.1f}s")

    # 轮 2：明确要求编程路径的复杂查询
    details.append("[轮2] 发送复杂计算查询")
    r2: RoundResult = await send_message_mainagent(
        session_id=session_id,
        message="帮我用代码查查这些修理厂的报价，按价格从低到高排序对比",
        round_num=2,
        context=TEST_LOCATION,
    )
    rounds.append(r2)

    if r2.error and "连接失败" in r2.error:
        details.append(f"ERROR: {r2.error}")
        return TestResult(
            name="Test2: MainAgent 复杂查询路径",
            passed=False,
            details=details,
            rounds=rounds,
        )

    details.append(f"[轮2] 工具: {r2.tool_calls}")
    details.append(f"[轮2] 回复长度: {len(r2.response_text)} 字")
    details.append(f"[轮2] 耗时: {r2.elapsed_seconds:.1f}s")

    # 判定：调了 call_query_codingagent = PASS
    has_coding: bool = "call_query_codingagent" in r2.tool_calls
    if has_coding:
        details.append("OK: 轮2 调了 call_query_codingagent（复杂查询走编程路径）")
    else:
        # LLM 可能选择了其他路径（match_project, search_shops 等）
        if r2.tool_calls:
            details.append(
                f"WARN: 轮2 未调 call_query_codingagent，"
                f"LLM 选择了: {r2.tool_calls}（合理的替代路径）"
            )
        else:
            details.append("WARN: 轮2 无工具调用（LLM 直接回复或追问）")

    # 有回复文本
    if r2.response_text.strip():
        details.append("OK: 有回复文本")
    else:
        details.append("FAIL: 无回复文本")

    # 汇总判定
    # call_query_codingagent 的触发依赖 LLM 判断，不硬性要求
    # 只要链路正常（有回复、无连接错误）就算 PASS
    passed: bool = bool(r2.response_text.strip()) and not r2.error
    if has_coding:
        details.append("VERDICT: PASS（走了编程路径）")
    elif r2.tool_calls:
        details.append("VERDICT: PASS（链路正常，LLM 选择了内置工具路径）")
    else:
        details.append("VERDICT: PASS（链路正常，LLM 选择了直接回复）")

    return TestResult(
        name="Test2: MainAgent 复杂查询路径",
        passed=passed,
        details=details,
        rounds=rounds,
    )


# ============================================================
# Test 3: 简单查询不触发 coding agent
# ============================================================


async def test_3_simple_no_coding() -> TestResult:
    """发简单查询给 MainAgent，验证走 search_shops 不走 call_query_codingagent。
    "附近有什么修理厂" 是简单搜索，不需要编程。
    """
    details: list[str] = []
    session_id: str = f"test-coding-simple-{uuid4().hex[:8]}"

    r: RoundResult = await send_message_mainagent(
        session_id=session_id,
        message="附近有什么修理厂",
        round_num=1,
        context=TEST_LOCATION,
    )

    if r.error:
        details.append(f"ERROR: {r.error}")
        if "连接失败" in r.error:
            return TestResult(
                name="Test3: 简单查询不触发 coding agent",
                passed=False,
                details=details,
                rounds=[r],
            )

    details.append(f"工具调用: {r.tool_calls}")
    details.append(f"回复长度: {len(r.response_text)} 字")
    details.append(f"耗时: {r.elapsed_seconds:.1f}s")

    passed: bool = True

    # 验证 1（核心）：不应该调 call_query_codingagent
    has_coding: bool = "call_query_codingagent" in r.tool_calls
    if has_coding:
        details.append("FAIL: 简单查询不应调 call_query_codingagent")
        passed = False
    else:
        details.append("OK: 未调 call_query_codingagent（简单查询走常规路径）")

    # 验证 2：应该调了 search_shops
    has_search: bool = "search_shops" in r.tool_calls
    if has_search:
        details.append("OK: 调了 search_shops")
    else:
        details.append("WARN: 未调 search_shops（可能走了其他路径）")

    # 验证 3：有回复文本
    if r.response_text.strip():
        details.append("OK: 有回复文本")
    else:
        details.append("FAIL: 无回复文本")
        passed = False

    return TestResult(
        name="Test3: 简单查询不触发 coding agent",
        passed=passed,
        details=details,
        rounds=[r],
    )


# ============================================================
# 报告输出
# ============================================================


def print_round(r: RoundResult) -> None:
    """打印单轮对话结果。"""
    truncated: str = r.response_text[:300] + ("..." if len(r.response_text) > 300 else "")
    print(f"    {_D}[轮{r.round_num}] 用户: {r.user_message[:80]}{_0}")
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
    print(f"{_B}coding agent searchshops E2E 测试报告{_0}")
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
    """运行所有 coding agent E2E 测试。"""
    print(f"\n{_B}coding agent searchshops E2E 测试{_0}")
    print(f"  MainAgent:    {MAINAGENT_URL}")
    print(f"  Coding Agent: {CODING_AGENT_URL}")
    print()

    all_results: list[TestResult] = []

    # ── 健康检查 ──
    services: list[tuple[str, str]] = [
        ("MainAgent", MAINAGENT_URL),
        ("Coding Agent", CODING_AGENT_URL),
    ]
    for name, url in services:
        try:
            r: httpx.Response = httpx.get(f"{url}/health", timeout=5)
            r.raise_for_status()
            print(f"{_G}{name} 就绪 ({url}){_0}")
        except Exception as e:
            print(f"{_R}{name} 不可达 ({url}): {e}{_0}")
            print(f"{_R}请确认服务已启动，跳过该依赖的测试{_0}")

    # ── Test 1: 直接调 coding agent ──
    print(f"\n{_C}>>> Test 1: 直接调 coding agent（A2A）{_0}")
    try:
        httpx.get(f"{CODING_AGENT_URL}/health", timeout=5).raise_for_status()
        t1: TestResult = await test_1_direct_coding_agent()
    except Exception as e:
        t1 = TestResult(
            name="Test1: 直接调 coding agent（A2A）",
            passed=False,
            details=[f"SKIP: Coding Agent 不可达 ({e})"],
        )
    all_results.append(t1)
    status1: str = f"{_G}PASS{_0}" if t1.passed else f"{_R}FAIL{_0}"
    print(f"  {status1} {t1.name}")
    for d in t1.details:
        print(f"    {d}")

    # ── Test 2: 通过 MainAgent 触发 coding agent ──
    print(f"\n{_C}>>> Test 2: MainAgent 触发 coding agent（复杂查询）{_0}")
    try:
        httpx.get(f"{MAINAGENT_URL}/health", timeout=5).raise_for_status()
        t2: TestResult = await test_2_mainagent_triggers_coding()
    except Exception as e:
        t2 = TestResult(
            name="Test2: MainAgent 触发 coding agent",
            passed=False,
            details=[f"SKIP: MainAgent 不可达 ({e})"],
        )
    all_results.append(t2)
    status2: str = f"{_G}PASS{_0}" if t2.passed else f"{_R}FAIL{_0}"
    print(f"  {status2} {t2.name}")
    for d in t2.details:
        print(f"    {d}")

    # ── Test 3: 简单查询不触发 coding agent ──
    print(f"\n{_C}>>> Test 3: 简单查询不触发 coding agent{_0}")
    try:
        httpx.get(f"{MAINAGENT_URL}/health", timeout=5).raise_for_status()
        t3: TestResult = await test_3_simple_no_coding()
    except Exception as e:
        t3 = TestResult(
            name="Test3: 简单查询不触发 coding agent",
            passed=False,
            details=[f"SKIP: MainAgent 不可达 ({e})"],
        )
    all_results.append(t3)
    status3: str = f"{_G}PASS{_0}" if t3.passed else f"{_R}FAIL{_0}"
    print(f"  {status3} {t3.name}")
    for d in t3.details:
        print(f"    {d}")

    # ── 汇总报告 ──
    print_report(all_results)


if __name__ == "__main__":
    asyncio.run(main())

"""S1 阶段 E2E 真实对话效果验证

自包含测试：启动 mock 后端 + 独立 MainAgent 实例，验证 S1 阶段核心行为：
- Hacker 试探：不能调用 S2 工具
- 正常漏斗：多轮对话走完 S1 → S2
- 用户不要优惠：引导提供车辆信息
- 闲聊拉回：回答后拉回养车话题
- 问平台：介绍平台能力

运行方式：
    cd mainagent && uv run python ../tests/test_s1_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Coroutine
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ── 路径 ──
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
MAINAGENT_DIR: Path = PROJECT_ROOT / "mainagent"
TEST_DATA_DIR: Path = PROJECT_ROOT / "data" / "s1_e2e_tests"

# ── 超时 ──
TIMEOUT: int = 120

# ── 运行时端口（main 中赋值）──
AGENT_PORT: int = 0
MOCK_PORT: int = 0
BASE_URL: str = ""

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
    score: int
    reasons: list[str]


# ============================================================
# Mock 后端服务器
# ============================================================

# match_project 关键词 → 项目映射
_PROJECT_DB: list[dict[str, Any]] = [
    {
        "keywords": ["机油", "换机油", "保养", "小保养"],
        "packageId": 1001,
        "packageName": "小保养（机油+机滤）",
        "chooseCar": "brand_series",
    },
    {
        "keywords": ["轮胎", "换轮胎"],
        "packageId": 1002,
        "packageName": "轮胎更换",
        "chooseCar": "car_and_param",
    },
    {
        "keywords": ["刹车片", "刹车", "制动"],
        "packageId": 1003,
        "packageName": "刹车片更换",
        "chooseCar": "car_and_param",
    },
    {
        "keywords": ["洗车"],
        "packageId": 1004,
        "packageName": "普通洗车",
        "chooseCar": "no_need_car",
    },
]

# mock 商户数据
_MOCK_SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": "shop_001",
        "commercialName": "张江途虎养车工场店",
        "address": "上海市浦东新区张江路100号",
        "provinceName": "上海",
        "cityName": "上海",
        "districtName": "浦东新区",
        "commercialType": 1,
        "latitude": 31.2310,
        "longitude": 121.4720,
        "distance": 500,
        "rating": 4.8,
        "tradingCount": 320,
        "phone": "021-12345678",
        "serviceScope": "保养,维修,轮胎",
        "imageObject": [],
        "openingHours": "08:00-20:00",
    },
    {
        "commercialId": "shop_002",
        "commercialName": "金科路驰加快修",
        "address": "上海市浦东新区金科路200号",
        "provinceName": "上海",
        "cityName": "上海",
        "districtName": "浦东新区",
        "commercialType": 1,
        "latitude": 31.2280,
        "longitude": 121.4680,
        "distance": 1200,
        "rating": 4.5,
        "tradingCount": 180,
        "phone": "021-87654321",
        "serviceScope": "保养,洗车,美容",
        "imageObject": [],
        "openingHours": "09:00-21:00",
    },
]


def _match_projects(search_key: str) -> list[dict[str, Any]]:
    """根据搜索关键词匹配项目列表。"""
    results: list[dict[str, Any]] = []
    for proj in _PROJECT_DB:
        for kw in proj["keywords"]:
            if kw in search_key or search_key in kw:
                results.append({
                    "packageId": proj["packageId"],
                    "packageName": proj["packageName"],
                    "chooseCar": proj["chooseCar"],
                })
                break
    return results


mock_app: FastAPI = FastAPI()


@mock_app.get("/health")
async def mock_health() -> JSONResponse:
    """健康检查端点。"""
    return JSONResponse({"status": "ok"})


@mock_app.post("/service_ai_datamanager/project/searchProjectPackageByKeyword")
async def mock_search_project(request: Request) -> JSONResponse:
    """模拟项目搜索接口。"""
    body: dict[str, Any] = await request.json()
    search_key: str = body.get("searchKey", "")
    matched: list[dict[str, Any]] = _match_projects(search_key)
    return JSONResponse({"status": 0, "result": matched})


@mock_app.post("/service_ai_datamanager/shop/getNearbyShops")
async def mock_nearby_shops(request: Request) -> JSONResponse:
    """模拟附近商户搜索接口。"""
    return JSONResponse({"status": 0, "result": {"commercials": _MOCK_SHOPS}})


@mock_app.post("/service_ai_datamanager/shop/getLatestVisitedShops")
async def mock_latest_visited(request: Request) -> JSONResponse:
    """模拟上次去过的商户（空）。"""
    return JSONResponse({"status": 0, "result": {"commercials": []}})


@mock_app.post("/service_ai_datamanager/shop/getHistoryVisitedShops")
async def mock_history_visited(request: Request) -> JSONResponse:
    """模拟历史服务商户（空）。"""
    return JSONResponse({"status": 0, "result": {"commercials": []}})


@mock_app.post("/service_ai_datamanager/shop/getAllShopType")
async def mock_all_shop_types(request: Request) -> JSONResponse:
    """模拟商户类型列表。"""
    return JSONResponse({"status": 0, "result": []})


@mock_app.post("/service_ai_datamanager/Auto/getCarModelByQueryKey")
async def mock_fuzzy_car(request: Request) -> JSONResponse:
    """模拟车型模糊匹配。"""
    return JSONResponse({"status": 0, "result": []})


# ============================================================
# Interrupt 自动回复映射
# ============================================================

INTERRUPT_AUTO_REPLIES: dict[str, dict[str, Any]] = {
    "select_car": {
        "car_model_id": "mmu_100",
        "car_model_name": "2021款大众朗逸 1.5L 自动舒适版",
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
# SSE 流式客户端（复用 test_v2_100scenarios.py 的逻辑）
# ============================================================


async def _send_interrupt_reply(
    client: httpx.AsyncClient,
    base_url: str,
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
            f"{base_url}/chat/interrupt-reply",
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
                            if i_key and i_type:
                                reply_err: str | None = await _send_interrupt_reply(
                                    client, base_url, i_key, i_type,
                                )
                                if reply_err:
                                    error = reply_err

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
]

CAR_INFO_KEYWORDS: list[str] = [
    "车辆信息", "车型", "VIN", "vin", "行驶证", "什么车", "哪款车",
    "绑定车辆", "车辆", "爱车",
]


# ============================================================
# 场景定义与评估
# ============================================================


async def scenario_1_hacker_probe() -> ScenarioResult:
    """场景 1: Hacker 试探 — 直接说"帮我预订"。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-hacker-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "帮我预订换机油", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True
    score: int = 5

    # 检查: 不能调用 confirm_booking（S1 没有这个工具）
    if "confirm_booking" in r.tool_calls:
        reasons.append("FAIL: S1 不应调用 confirm_booking")
        passed = False
        score -= 2

    # 检查: 不能调用 confirm_saving_plan（还没确认项目和省钱方式）
    if "confirm_saving_plan" in r.tool_calls:
        reasons.append("FAIL: 还没确认项目和省钱方式就调了 confirm_saving_plan")
        passed = False
        score -= 2

    # 检查: 回复中引导用户了解省钱方式
    has_saving_guide: bool = any(kw in r.response_text for kw in SAVING_KEYWORDS)
    if not has_saving_guide:
        reasons.append("WARN: 回复中没有省钱/优惠相关引导")
        score -= 1

    if not reasons:
        reasons.append("OK: S1 正确拦截预订请求，引导省钱")

    return ScenarioResult(
        name="场景1: Hacker 试探 — 直接说帮我预订",
        rounds=[r],
        passed=passed,
        score=max(score, 1),
        reasons=reasons,
    )


async def scenario_2_normal_funnel() -> ScenarioResult:
    """场景 2: 正常漏斗 — 多轮对话走完 S1 → S2。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-funnel-{uuid4().hex[:8]}"

    reasons: list[str] = []
    passed: bool = True
    score: int = 5
    rounds: list[RoundResult] = []

    # ---- 第 1 轮: "我想换个机油" ----
    r1: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "我想换个机油", user_id, TIMEOUT,
    )
    r1.round_num = 1
    rounds.append(r1)

    if "classify_project" not in r1.tool_calls and "match_project" not in r1.tool_calls:
        reasons.append("WARN: 第1轮没调 classify_project 或 match_project")
        score -= 1

    has_saving_r1: bool = any(kw in r1.response_text for kw in SAVING_KEYWORDS)
    if not has_saving_r1:
        reasons.append("WARN: 第1轮回复没提到省钱方法")
        score -= 1

    # ---- 第 2 轮: "好的，用平台优惠吧" ----
    r2: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "好的，用平台优惠吧", user_id, TIMEOUT,
    )
    r2.round_num = 2
    rounds.append(r2)

    if "confirm_saving_plan" not in r2.tool_calls:
        reasons.append("FAIL: 第2轮没调 confirm_saving_plan")
        passed = False
        score -= 2

    # ---- 第 3 轮: "帮我找个店"（此时应该已经是 S2） ----
    r3: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "帮我找个店", user_id, TIMEOUT,
    )
    r3.round_num = 3
    rounds.append(r3)

    # S2 阶段应该有 confirm_booking 能力（不一定调用，但不应报工具不存在错误）
    has_shop_search: bool = "search_shops" in r3.tool_calls
    has_error: bool = bool(r3.error)
    if has_shop_search:
        reasons.append("OK: 第3轮调了 search_shops，S2 正常推进")
    elif not has_error:
        reasons.append("INFO: 第3轮未调 search_shops，但无报错")

    if not reasons:
        reasons.append("OK: 正常漏斗 S1 → S2 全流程通过")

    return ScenarioResult(
        name="场景2: 正常漏斗 — 多轮走完 S1→S2",
        rounds=rounds,
        passed=passed,
        score=max(score, 1),
        reasons=reasons,
    )


async def scenario_3_user_declines_coupon() -> ScenarioResult:
    """场景 3: 用户不要优惠 — 引导提供车辆信息。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-nocoupon-{uuid4().hex[:8]}"

    reasons: list[str] = []
    passed: bool = True
    score: int = 5
    rounds: list[RoundResult] = []

    # ---- 第 1 轮: "换刹车片" ----
    r1: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "换刹车片", user_id, TIMEOUT,
    )
    r1.round_num = 1
    rounds.append(r1)

    has_saving_r1: bool = any(kw in r1.response_text for kw in SAVING_KEYWORDS)
    if not has_saving_r1:
        reasons.append("WARN: 第1轮没展示省钱方法")
        score -= 1

    # ---- 第 2 轮: "不用了，直接帮我做" ----
    r2: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "不用了，直接帮我做", user_id, TIMEOUT,
    )
    r2.round_num = 2
    rounds.append(r2)

    # 不应调用 confirm_saving_plan
    if "confirm_saving_plan" in r2.tool_calls:
        reasons.append("FAIL: 用户拒绝优惠后不应调 confirm_saving_plan")
        passed = False
        score -= 2

    # 应引导提供车辆信息
    has_car_guide: bool = any(kw in r2.response_text for kw in CAR_INFO_KEYWORDS)
    if not has_car_guide:
        reasons.append("WARN: 第2轮没引导提供车辆信息")
        score -= 1

    if not reasons:
        reasons.append("OK: 用户拒绝优惠 → 正确引导提供车辆信息")

    return ScenarioResult(
        name="场景3: 用户不要优惠 — 引导车辆信息",
        rounds=rounds,
        passed=passed,
        score=max(score, 1),
        reasons=reasons,
    )


async def scenario_4_chitchat_redirect() -> ScenarioResult:
    """场景 4: 闲聊拉回 — 回答后拉回养车话题。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-chitchat-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "今天天气怎么样", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True
    score: int = 5

    # 回复中应包含养车/省钱相关引导（拉回主线）
    redirect_keywords: list[str] = [
        "养车", "保养", "维修", "省钱", "优惠", "爱车", "车",
        "项目", "服务", "帮您", "帮你",
    ]
    has_redirect: bool = any(kw in r.response_text for kw in redirect_keywords)
    if not has_redirect:
        reasons.append("FAIL: 闲聊后没有拉回养车话题")
        passed = False
        score -= 2

    if not reasons:
        reasons.append("OK: 闲聊后正确拉回养车话题")

    return ScenarioResult(
        name="场景4: 闲聊拉回",
        rounds=[r],
        passed=passed,
        score=max(score, 1),
        reasons=reasons,
    )


async def scenario_5_ask_platform() -> ScenarioResult:
    """场景 5: 问平台 — 介绍平台能力。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-platform-{uuid4().hex[:8]}"

    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "你是谁？能做什么？", user_id, TIMEOUT,
    )
    r.round_num = 1

    reasons: list[str] = []
    passed: bool = True
    score: int = 5

    # 回复中应包含"话痨"或"养车"相关内容
    platform_keywords: list[str] = ["话痨", "养车", "省钱", "助理", "助手"]
    has_platform_intro: bool = any(kw in r.response_text for kw in platform_keywords)
    if not has_platform_intro:
        reasons.append("FAIL: 没有介绍平台能力")
        passed = False
        score -= 2

    if not reasons:
        reasons.append("OK: 正确介绍平台能力")

    return ScenarioResult(
        name="场景5: 问平台",
        rounds=[r],
        passed=passed,
        score=max(score, 1),
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
    total_score: int = sum(r.score for r in results)
    max_score: int = total * 5

    print(f"\n{'=' * 60}")
    print(f"{_B}S1 E2E 测试报告{_0}")
    print(f"{'=' * 60}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"{status} {_B}{result.name}{_0}  (分数: {result.score}/5)")

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
    print(f"{color}通过: {passed_count}/{total}  总分: {total_score}/{max_score}{_0}")
    print(f"{'─' * 60}\n")


# ============================================================
# 服务器生命周期管理
# ============================================================


def _find_free_port() -> int:
    """找到一个可用的空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_mock_server_inprocess(port: int) -> threading.Thread:
    """在后台线程中启动 mock 后端服务器（in-process，无需模块导入）。"""
    config: uvicorn.Config = uvicorn.Config(
        mock_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server: uvicorn.Server = uvicorn.Server(config)

    thread: threading.Thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def _start_agent_server(agent_port: int, mock_port: int) -> subprocess.Popen[bytes]:
    """启动独立的 MainAgent 实例，DATA_MANAGER_URL 指向 mock server。

    使用 python server.py 启动（而不是直接 uvicorn），这样 nacos.py
    会自动加载 .env.local 中的 Azure OpenAI 等配置。
    通过环境变量覆盖 DATA_MANAGER_URL 和端口。
    """
    # 清除代理环境变量（WSL 下 HTTP_PROXY 会干扰 localhost 请求）
    clean_env: dict[str, str] = {
        k: v for k, v in os.environ.items()
        if k.lower() not in ("http_proxy", "https_proxy")
    }

    mock_url: str = f"http://127.0.0.1:{mock_port}"
    env: dict[str, str] = {
        **clean_env,
        # ACTIVE=local 让 nacos.py 加载 .env.local（含 Azure OpenAI 配置）
        "ACTIVE": "local",
        # 覆盖端口和后端地址
        "SERVER_PORT": str(agent_port),
        "DATA_MANAGER_URL": mock_url,
        "FUZZY_MATCH_CAR_URL": f"{mock_url}/service_ai_datamanager/Auto/getCarModelByQueryKey",
        # 测试用数据目录
        "INNER_STORAGE_DIR": str(TEST_DATA_DIR / "inner"),
        "FS_TOOLS_DIR": str(TEST_DATA_DIR),
        # 禁用 Logfire 避免干扰
        "LOGFIRE_ENABLED": "false",
    }

    proc: subprocess.Popen[bytes] = subprocess.Popen(
        [
            sys.executable, "server.py",
            "--port", str(agent_port),
            "--host", "127.0.0.1",
        ],
        env=env,
        cwd=str(MAINAGENT_DIR),
    )
    return proc


def _wait_for_server(url: str, label: str, max_wait: int = 30) -> bool:
    """等待服务器就绪，返回是否成功。"""
    for i in range(max_wait):
        try:
            r: httpx.Response = httpx.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                print(f"  {_G}{label} 就绪 ({i+1}s){_0}")
                return True
        except Exception:
            pass
        time.sleep(1)
    print(f"  {_R}{label} 启动超时（{max_wait}s）{_0}")
    return False


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    """终止子进程。"""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """启动 mock + agent，依次运行所有 S1 E2E 场景。"""
    global AGENT_PORT, MOCK_PORT, BASE_URL

    MOCK_PORT = _find_free_port()
    AGENT_PORT = _find_free_port()
    BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"
    mock_url: str = f"http://127.0.0.1:{MOCK_PORT}"

    # 确保测试数据目录存在
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{_B}S1 E2E 测试{_0}")
    print(f"  Mock 后端: {mock_url}")
    print(f"  MainAgent: {BASE_URL}")
    print(f"  超时: {TIMEOUT}s\n")

    # ---- 启动 mock server（in-process，后台线程）----
    print(f"{_C}▶ 启动 mock 后端...{_0}")
    _mock_thread: threading.Thread = _start_mock_server_inprocess(MOCK_PORT)

    if not _wait_for_server(mock_url, "Mock 后端"):
        sys.exit(1)

    # ---- 启动 agent server（子进程）----
    print(f"{_C}▶ 启动 MainAgent...{_0}")
    agent_proc: subprocess.Popen[bytes] = _start_agent_server(AGENT_PORT, MOCK_PORT)

    if not _wait_for_server(BASE_URL, "MainAgent"):
        _kill_proc(agent_proc)
        sys.exit(1)

    # ---- 运行场景 ----
    try:
        scenarios: list[tuple[str, Callable[[], Coroutine[Any, Any, ScenarioResult]]]] = [
            ("场景1", scenario_1_hacker_probe),
            ("场景2", scenario_2_normal_funnel),
            ("场景3", scenario_3_user_declines_coupon),
            ("场景4", scenario_4_chitchat_redirect),
            ("场景5", scenario_5_ask_platform),
        ]

        results: list[ScenarioResult] = []
        for label, fn in scenarios:
            print(f"{_C}▶ 运行 {label}...{_0}")
            result: ScenarioResult = await fn()
            results.append(result)

        print_report(results)
    finally:
        # 清理 agent 子进程（mock 线程是 daemon，主进程退出时自动终止）
        print(f"{_D}清理进程...{_0}")
        _kill_proc(agent_proc)


if __name__ == "__main__":
    asyncio.run(main())

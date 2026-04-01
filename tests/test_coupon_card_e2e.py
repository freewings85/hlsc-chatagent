"""CouponCard E2E 测试：验证 search_coupon 查到优惠后 agent 输出 CouponCard spec 卡片。

自包含测试：启动 mock DataManager + 独立 MainAgent 实例，
发消息"洗车有什么优惠"，检查 SSE 返回中包含 CouponCard spec 块。

运行方式：
    cd mainagent && uv run python ../tests/test_coupon_card_e2e.py
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ── 路径 ──
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
MAINAGENT_DIR: Path = PROJECT_ROOT / "mainagent"
TEST_DATA_DIR: Path = PROJECT_ROOT / "data" / "coupon_card_e2e"

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


# ============================================================
# Mock DataManager 服务器
# ============================================================

mock_app: FastAPI = FastAPI()


@mock_app.get("/health")
async def mock_health() -> JSONResponse:
    """健康检查端点。"""
    return JSONResponse({"status": "ok"})


# classify_project 使用的端点
@mock_app.post("/service_ai_datamanager/package/searchPackageByKeyword")
async def mock_classify_project(request: Request) -> JSONResponse:
    """模拟 classify_project 的项目搜索接口。

    classify_project 发送 {"keyword": "...", "top_k": 5}，
    返回 packageId / packageName。
    """
    body: dict[str, Any] = await request.json()
    keyword: str = body.get("keyword", "")
    print(f"  {_D}[mock] classify_project keyword={keyword}{_0}")

    # 洗车关键词命中
    if "洗车" in keyword or "洗" in keyword:
        return JSONResponse({
            "status": 0,
            "message": "执行成功",
            "result": [
                {"packageId": 1004, "packageName": "普通洗车", "path": "洗车美容", "last": True},
            ],
        })

    # 默认空
    return JSONResponse({"status": 0, "message": "执行成功", "result": []})


# match_project 使用的端点（S2 阶段，这里也 mock 以防万一）
@mock_app.post("/service_ai_datamanager/project/searchProjectPackageByKeyword")
async def mock_match_project(request: Request) -> JSONResponse:
    """模拟 match_project 的项目搜索接口。"""
    body: dict[str, Any] = await request.json()
    search_key: str = body.get("searchKey", "")
    print(f"  {_D}[mock] match_project searchKey={search_key}{_0}")

    if "洗车" in search_key or "洗" in search_key:
        return JSONResponse({
            "status": 0,
            "message": "执行成功",
            "result": [
                {"packageId": 1004, "packageName": "普通洗车", "path": "洗车美容", "last": True},
            ],
        })
    return JSONResponse({"status": 0, "message": "执行成功", "result": []})


# search_coupon 使用的端点
@mock_app.post("/service_ai_datamanager/Discount/recommend")
async def mock_discount_recommend(request: Request) -> JSONResponse:
    """模拟优惠活动查询接口。

    返回 platformActivities 和 shopActivities，
    每条包含 activityId、activityName、shopId、shopName。
    """
    body: dict[str, Any] = await request.json()
    print(f"  {_D}[mock] Discount/recommend body={body}{_0}")

    return JSONResponse({
        "status": 0,
        "message": "执行成功",
        "result": {
            "platformActivities": [
                {
                    "activityId": 35,
                    "activityName": "5元抵20元",
                    "shopId": 100,
                    "shopName": "话痨平台",
                },
            ],
            "shopActivities": [
                {
                    "activityId": 88,
                    "activityName": "保养满300减50",
                    "shopId": 53,
                    "shopName": "张江汽修中心",
                },
            ],
        },
    })


# 其他可能被调用的端点（兜底 mock）
@mock_app.post("/service_ai_datamanager/shop/getNearbyShops")
async def mock_nearby_shops(request: Request) -> JSONResponse:
    """模拟附近商户搜索接口。"""
    return JSONResponse({"status": 0, "result": {"commercials": []}})


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
# SSE 流式客户端
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
# 服务器生命周期管理
# ============================================================


def _find_free_port() -> int:
    """找到一个可用的空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_mock_server_inprocess(port: int) -> threading.Thread:
    """在后台线程中启动 mock DataManager（in-process，无需模块导入）。"""
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
    """启动独立的 MainAgent 实例，DATA_MANAGER_URL 指向 mock server。"""
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
# CouponCard 验证
# ============================================================


def check_coupon_card_in_response(response_text: str) -> tuple[bool, list[str]]:
    """检查响应文本中是否包含有效的 CouponCard spec 块。

    返回 (是否找到, 详细原因列表)。
    """
    reasons: list[str] = []

    # 检查 spec 代码块是否存在
    if "```spec" not in response_text:
        reasons.append("FAIL: 响应中没有 ```spec 代码块")
        return False, reasons

    # 提取 spec 块中的内容
    spec_blocks: list[str] = []
    in_spec: bool = False
    current_block: list[str] = []
    for line in response_text.split("\n"):
        stripped: str = line.strip()
        if stripped == "```spec":
            in_spec = True
            current_block = []
        elif stripped == "```" and in_spec:
            in_spec = False
            spec_blocks.append("\n".join(current_block))
        elif in_spec:
            current_block.append(line)

    if not spec_blocks:
        reasons.append("FAIL: spec 代码块内容为空")
        return False, reasons

    # 在所有 spec 块中查找 CouponCard
    coupon_cards: list[dict[str, Any]] = []
    for block in spec_blocks:
        for line in block.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj: dict[str, Any] = json.loads(line)
                if obj.get("type") == "CouponCard":
                    coupon_cards.append(obj)
            except json.JSONDecodeError:
                continue

    if not coupon_cards:
        reasons.append("FAIL: spec 块中没有 CouponCard 类型的卡片")
        return False, reasons

    reasons.append(f"OK: 找到 {len(coupon_cards)} 个 CouponCard")

    # 验证每个 CouponCard 的 props 字段
    required_props: list[str] = ["shop_id", "shop_name", "activity_id", "activity_name"]
    all_valid: bool = True
    for i, card in enumerate(coupon_cards):
        props: dict[str, Any] = card.get("props", {})
        missing: list[str] = [p for p in required_props if p not in props]
        if missing:
            reasons.append(f"FAIL: CouponCard[{i}] 缺少 props: {missing}")
            all_valid = False
        else:
            reasons.append(
                f"OK: CouponCard[{i}] props 完整 — "
                f"activity_id={props['activity_id']}, "
                f"activity_name={props['activity_name']}, "
                f"shop_id={props['shop_id']}, "
                f"shop_name={props['shop_name']}"
            )

    return all_valid, reasons


# ============================================================
# 主测试流程
# ============================================================


async def run_coupon_card_test() -> bool:
    """执行 CouponCard E2E 测试，返回是否通过。"""
    session_id: str = str(uuid4())
    user_id: str = f"e2e-coupon-{uuid4().hex[:8]}"

    print(f"\n{_C}▶ 发送消息: '洗车有什么优惠'{_0}")

    # 第 1 轮："洗车有什么优惠"
    # agent 应该：
    #   1. 调 classify_project 识别"洗车"
    #   2. 调 search_coupon 查优惠
    #   3. 用 CouponCard spec 输出优惠卡片
    r: RoundResult = await chat_stream_with_interrupt(
        BASE_URL, session_id, "洗车有什么优惠", user_id, TIMEOUT,
    )
    r.round_num = 1

    # ---- 打印结果 ----
    print(f"\n{_B}对话结果:{_0}")
    print(f"  {_D}用户: {r.user_message}{_0}")
    truncated: str = r.response_text[:500] + ("..." if len(r.response_text) > 500 else "")
    print(f"  {_D}回复: {truncated}{_0}")
    if r.tool_calls:
        print(f"  {_C}工具调用: {', '.join(r.tool_calls)}{_0}")
    if r.interrupts:
        i_types: list[str] = [i["type"] for i in r.interrupts]
        print(f"  {_Y}Interrupt: {', '.join(i_types)}{_0}")
    if r.error:
        print(f"  {_R}错误: {r.error}{_0}")
    print(f"  {_D}耗时: {r.elapsed_seconds:.1f}s{_0}")

    # ---- 评估 ----
    passed: bool = True
    all_reasons: list[str] = []

    # 检查 1: 是否调了 classify_project
    if "classify_project" in r.tool_calls:
        all_reasons.append("OK: 调了 classify_project")
    else:
        all_reasons.append("WARN: 没调 classify_project（可能用了 match_project 或其他方式）")

    # 检查 2: 是否调了 search_coupon
    if "search_coupon" in r.tool_calls:
        all_reasons.append("OK: 调了 search_coupon")
    else:
        all_reasons.append("FAIL: 没调 search_coupon — 无法展示优惠卡片")
        passed = False

    # 检查 3: 响应中是否包含 CouponCard spec
    card_found: bool
    card_reasons: list[str]
    card_found, card_reasons = check_coupon_card_in_response(r.response_text)
    all_reasons.extend(card_reasons)
    if not card_found:
        passed = False

    # 检查 4: 有无错误
    if r.error:
        all_reasons.append(f"WARN: 有错误: {r.error}")

    # ---- 打印报告 ----
    print(f"\n{'=' * 60}")
    print(f"{_B}CouponCard E2E 测试报告{_0}")
    print(f"{'=' * 60}\n")

    status: str = f"{_G}PASS{_0}" if passed else f"{_R}FAIL{_0}"
    print(f"{status} {_B}search_coupon → CouponCard spec 输出{_0}\n")

    for reason in all_reasons:
        if reason.startswith("FAIL"):
            print(f"  {_R}{reason}{_0}")
        elif reason.startswith("WARN"):
            print(f"  {_Y}{reason}{_0}")
        else:
            print(f"  {_G}{reason}{_0}")

    print(f"\n{'─' * 60}")
    color: str = _G if passed else _R
    print(f"{color}结果: {'PASS' if passed else 'FAIL'}{_0}")
    print(f"{'─' * 60}\n")

    # 打印完整响应以便调试
    print(f"{_D}完整响应文本:{_0}")
    print(f"{_D}{'─' * 40}{_0}")
    print(r.response_text)
    print(f"{_D}{'─' * 40}{_0}")

    return passed


async def main() -> None:
    """启动 mock + agent，运行 CouponCard E2E 测试。"""
    global AGENT_PORT, MOCK_PORT, BASE_URL

    MOCK_PORT = _find_free_port()
    AGENT_PORT = _find_free_port()
    BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"
    mock_url: str = f"http://127.0.0.1:{MOCK_PORT}"

    # 确保测试数据目录存在
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{_B}CouponCard E2E 测试{_0}")
    print(f"  Mock DataManager: {mock_url}")
    print(f"  MainAgent: {BASE_URL}")
    print(f"  超时: {TIMEOUT}s\n")

    # ---- 启动 mock server（in-process，后台线程）----
    print(f"{_C}▶ 启动 mock DataManager...{_0}")
    _mock_thread: threading.Thread = _start_mock_server_inprocess(MOCK_PORT)

    if not _wait_for_server(mock_url, "Mock DataManager"):
        sys.exit(1)

    # ---- 启动 agent server（子进程）----
    print(f"{_C}▶ 启动 MainAgent...{_0}")
    agent_proc: subprocess.Popen[bytes] = _start_agent_server(AGENT_PORT, MOCK_PORT)

    if not _wait_for_server(BASE_URL, "MainAgent"):
        _kill_proc(agent_proc)
        sys.exit(1)

    # ---- 运行测试 ----
    try:
        passed: bool = await run_coupon_card_test()
        exit_code: int = 0 if passed else 1
    finally:
        # 清理 agent 子进程（mock 线程是 daemon，主进程退出时自动终止）
        print(f"{_D}清理进程...{_0}")
        _kill_proc(agent_proc)

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())

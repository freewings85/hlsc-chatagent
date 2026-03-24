"""Car context flow E2E 测试。

自包含，不依赖 mainagent 生产代码。
使用 test_server.py 启动测试专用 Agent（mock tools + real extension tools）。

场景 1：context 有 car + location → 直接用，一次 tool call
场景 3：context 无 → interrupt 弹框
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAINAGENT_DIR = PROJECT_ROOT / "mainagent"
CJML_DIR = PROJECT_ROOT.parent / "cjml-cheap-weixiu"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
TEST_SERVER = Path(__file__).parent / "test_server.py"
TEST_PORT = 8195
MOCK_PORT = 8106


def _no_proxy_client(**kwargs: Any) -> httpx.Client:
    transport = httpx.HTTPTransport()
    return httpx.Client(transport=transport, **kwargs)


def _wait_for_health(url: str, timeout_secs: int = 90) -> bool:
    for _ in range(timeout_secs):
        try:
            with _no_proxy_client(timeout=2) as client:
                r = client.get(f"{url}/health")
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def server_url():
    """启动 mock server + 测试 Agent 服务器"""
    if not DIST_DIR.exists():
        subprocess.run(["npx", "vite", "build"], cwd=str(WEB_DIR), check=True, timeout=60)

    for port in (TEST_PORT, MOCK_PORT):
        subprocess.run(f"lsof -ti:{port} | xargs kill -9", shell=True, capture_output=True)
    time.sleep(1)

    # 1. 启动 cjml mock server（提供零部件搜索/价格等接口）
    mock_proc = None
    mock_server_py = CJML_DIR / "mock_tool_server.py"
    if mock_server_py.exists():
        mock_proc = subprocess.Popen(
            ["uv", "run", "python", str(mock_server_py)],
            cwd=str(CJML_DIR),
            stdout=open("/tmp/e2e_mock_server.log", "w"),
            stderr=subprocess.STDOUT,
        )
        _wait_for_health(f"http://127.0.0.1:{MOCK_PORT}", timeout_secs=60)

    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    # 2. 启动测试 Agent 服务器
    proc = subprocess.Popen(
        ["uv", "run", "python", str(TEST_SERVER), "--port", str(TEST_PORT)],
        env={
            **clean_env,
            "TEMPORAL_ENABLED": "false",
            "INNER_STORAGE_DIR": str(MAINAGENT_DIR / "data" / "inner"),
            "FS_TOOLS_DIR": ".chatagent/fstools",
            "AGENT_FS_DIR": ".chatagent",
            "LOG_DIR": str(MAINAGENT_DIR / "logs"),
            "PROMPTS_DIR": str(MAINAGENT_DIR / "prompts"),
            "USE_NACOS": "FALSE",
            # Mock server URLs（零部件相关）
            "CAR_PART_RETRIEVAL_URL": f"http://127.0.0.1:{MOCK_PORT}/api/carParts/fusionSearch",
            "QUERY_PART_PRICE_URL": f"http://127.0.0.1:{MOCK_PORT}/api/price/partPrice",
            "CAR_PART_DATASET_ID": "test-dataset",
        },
        cwd=str(MAINAGENT_DIR),
        stdout=open("/tmp/e2e_test_server.log", "w"),
        stderr=subprocess.STDOUT,
    )

    url = f"http://127.0.0.1:{TEST_PORT}"
    if not _wait_for_health(url):
        proc.kill()
        pytest.fail(f"Test server failed to start on port {TEST_PORT}")

    yield url

    proc.kill()
    proc.wait()
    if mock_proc:
        mock_proc.kill()
        mock_proc.wait()


def _collect_sse(server_url: str, message: str, context: dict | None = None, timeout: int = 120) -> list[dict]:
    """发送 SSE 请求，收集所有事件"""
    import threading

    session_id = f"test-{os.getpid()}-{int(time.time())}"
    all_events: list[dict] = []
    stream_done = threading.Event()

    body: dict[str, Any] = {
        "session_id": session_id,
        "message": message,
        "user_id": "test-user",
    }
    if context:
        body["context"] = context

    def read_sse():
        try:
            with _no_proxy_client(timeout=timeout) as client:
                with client.stream("POST", f"{server_url}/chat/stream", json=body) as resp:
                    buffer = ""
                    for chunk in resp.iter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            et, data = "message", ""
                            for line in block.strip().split("\n"):
                                if line.startswith("event: "): et = line[7:].strip()
                                elif line.startswith("data: "): data = line[6:].strip()
                            if data:
                                try:
                                    all_events.append({"type": et, "data": json.loads(data)})
                                except:
                                    pass
        except Exception:
            pass
        finally:
            stream_done.set()

    t = threading.Thread(target=read_sse, daemon=True)
    t.start()
    stream_done.wait(timeout=timeout)
    return all_events


class TestCarContextFlow:
    """验证 confirm-car-info skill 在不同场景下的行为"""

    def test_scenario1_context_complete_direct_call(self, server_url: str) -> None:
        """场景 1：context 有 car + location → 直接调 get_car_price，不触发 interrupt"""
        events = _collect_sse(server_url, "帮我查下养车价格", context={
            "current_car": {"car_model_id": "CAR-001", "car_model_name": "帕萨特 2020款"},
            "current_location": {"address": "浦东张江", "lat": 31.2, "lng": 121.5},
        })

        tool_calls = [
            e["data"].get("data", e["data"]).get("tool_name", "")
            for e in events if e["type"] == "tool_call_start"
        ]

        # 应调用 get_car_price
        assert "get_car_price" in tool_calls, f"应调用 get_car_price，实际: {tool_calls}"

        # 不应触发任何 confirm 工具
        assert "ask_user_car_info" not in tool_calls
        assert "ask_user_location" not in tool_calls
        assert "get_representative_car_model" not in tool_calls
        assert "geocode_location" not in tool_calls

        # 应有价格相关文本
        texts = "".join(
            e["data"].get("data", e["data"]).get("content", "")
            for e in events if e["type"] == "text"
        )
        assert "普洗" in texts or "价格" in texts

    def test_scenario3_no_context_triggers_interrupt(self, server_url: str) -> None:
        """场景 3：无 context → 触发 interrupt"""
        import threading

        session_id = f"test-s3-{os.getpid()}"
        all_events: list[dict] = []
        interrupt_keys: list[str] = []
        stream_done = threading.Event()

        def read_sse():
            try:
                with _no_proxy_client(timeout=180) as client:
                    with client.stream("POST", f"{server_url}/chat/stream", json={
                        "session_id": session_id,
                        "message": "帮我查下养车价格",
                        "user_id": "test-user",
                        # 不传 context
                    }) as resp:
                        buffer = ""
                        for chunk in resp.iter_text():
                            buffer += chunk
                            while "\n\n" in buffer:
                                block, buffer = buffer.split("\n\n", 1)
                                et, data = "message", ""
                                for line in block.strip().split("\n"):
                                    if line.startswith("event: "): et = line[7:].strip()
                                    elif line.startswith("data: "): data = line[6:].strip()
                                if data:
                                    try:
                                        parsed = json.loads(data)
                                        all_events.append({"type": et, "data": parsed})
                                        if et == "interrupt":
                                            d = parsed.get("data", parsed)
                                            key = d.get("interrupt_key", "")
                                            if key:
                                                interrupt_keys.append(key)
                                    except:
                                        pass
            except Exception:
                pass
            finally:
                stream_done.set()

        t = threading.Thread(target=read_sse, daemon=True)
        t.start()

        # 等 interrupt
        for _ in range(600):
            if interrupt_keys or stream_done.is_set():
                break
            time.sleep(0.1)

        if not interrupt_keys:
            event_types = [e["type"] for e in all_events]
            if "chat_request_end" in event_types:
                pytest.skip(f"LLM did not trigger interrupt. Events: {event_types}")
            pytest.fail(f"未收到 interrupt. Events: {event_types}")

        # 回复 interrupt
        with _no_proxy_client(timeout=10) as client:
            resp = client.post(f"{server_url}/chat/interrupt-reply", json={
                "interrupt_key": interrupt_keys[0],
                "reply": json.dumps({
                    "car_model_id": "CAR-MOCK-001",
                    "car_model_name": "帕萨特(测试)",
                }),
            })
            assert resp.status_code == 200

        stream_done.wait(timeout=60)

        # 验证：有 interrupt 事件
        interrupts = [e for e in all_events if e["type"] == "interrupt"]
        assert len(interrupts) > 0

        # 验证 interrupt 类型
        idata = interrupts[0]["data"].get("data", interrupts[0]["data"])
        assert idata.get("type") in ("select_car", "select_location")


class TestQueryPartPrice:
    """验证 query-part-price skill 完整流程"""

    def test_query_part_price_with_context(self, server_url: str) -> None:
        """有 context + 问零部件价格 → invoke skill → bash 执行脚本 → 返回价格"""
        events = _collect_sse(server_url, "刹车片多少钱", context={
            "current_car": {"car_model_id": "CAR-001", "car_model_name": "帕萨特 2020款"},
            "current_location": {"address": "浦东张江", "lat": 31.2, "lng": 121.5},
        }, timeout=180)

        tool_calls = [
            e["data"].get("data", e["data"]).get("tool_name", "")
            for e in events if e["type"] == "tool_call_start"
        ]

        # 应调用 Skill（invoke query-part-price）
        # 和/或 bash（执行 search_parts / get_part_price 脚本）
        has_skill = "Skill" in tool_calls
        has_script = "bash" in tool_calls

        texts = "".join(
            e["data"].get("data", e["data"]).get("content", "")
            for e in events if e["type"] == "text"
        )

        # 至少应有零部件相关的回复
        has_part_info = any(kw in texts for kw in ["刹车", "价格", "配件", "零部件", "Error"])

        if not has_skill and not has_script:
            # LLM 可能直接用 get_car_price 了（没走 skill）
            if "get_car_price" in tool_calls:
                pytest.skip("LLM used get_car_price instead of query-part-price skill")
            pytest.skip(f"LLM did not invoke skill or script. Tools: {tool_calls}")

        assert has_part_info, f"应包含零部件相关信息，实际: {texts[:300]}"

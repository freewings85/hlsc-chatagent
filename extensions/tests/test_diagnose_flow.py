"""诊断 Agent E2E 测试 — mainagent → diagnose_agent → mock fault API。

自包含，使用 test_server.py + diagnose_agent + cjml mock server。
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
DIAGNOSE_DIR = PROJECT_ROOT / "subagents" / "diagnose_agent"
CJML_DIR = PROJECT_ROOT.parent / "cjml-cheap-weixiu"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
TEST_SERVER = Path(__file__).parent / "test_server.py"

MAIN_PORT = 8194
DIAGNOSE_PORT = 8103
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
    """启动 mock server + diagnose_agent + mainagent(test_server)"""
    if not DIST_DIR.exists():
        subprocess.run(["npx", "vite", "build"], cwd=str(WEB_DIR), check=True, timeout=60)

    for port in (MAIN_PORT, DIAGNOSE_PORT, MOCK_PORT):
        subprocess.run(f"lsof -ti:{port} | xargs kill -9", shell=True, capture_output=True)
    time.sleep(1)

    procs = []
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    # 1. cjml mock server
    mock_server_py = CJML_DIR / "mock_tool_server.py"
    if not mock_server_py.exists():
        pytest.skip("cjml-cheap-weixiu mock_tool_server.py not found")

    mock_proc = subprocess.Popen(
        ["uv", "run", "python", str(mock_server_py)],
        cwd=str(CJML_DIR),
        stdout=open("/tmp/e2e_diag_mock.log", "w"),
        stderr=subprocess.STDOUT,
    )
    procs.append(mock_proc)
    if not _wait_for_health(f"http://127.0.0.1:{MOCK_PORT}", timeout_secs=90):
        for p in procs:
            p.kill()
        pytest.fail("Mock server failed to start")

    # 2. diagnose_agent
    diag_proc = subprocess.Popen(
        ["uv", "run", "python", "server.py", "--port", str(DIAGNOSE_PORT)],
        env={
            **clean_env,
            "TEMPORAL_ENABLED": "false",
            "INNER_STORAGE_DIR": "data/inner",
            "FS_TOOLS_DIR": "data/fstools",
            "AGENT_FS_DIR": ".chatagent",
            "LOG_DIR": "logs",
            "PROMPTS_DIR": "prompts",
            "USE_NACOS": "FALSE",
            "CAR_FAULT_RETRIEVAL_URL": f"http://127.0.0.1:{MOCK_PORT}/api/faultSearch/retrieval",
            "CAR_FAULT_DATASET_IDS": "default",
            "GET_PART_PRIMARY_URL": f"http://127.0.0.1:{MOCK_PORT}/getPartPrimary",
            "GET_PROJECT_BYCAR_URL": f"http://127.0.0.1:{MOCK_PORT}/getProjectBycar",
        },
        cwd=str(DIAGNOSE_DIR),
        stdout=open("/tmp/e2e_diag_agent.log", "w"),
        stderr=subprocess.STDOUT,
    )
    procs.append(diag_proc)
    if not _wait_for_health(f"http://127.0.0.1:{DIAGNOSE_PORT}", timeout_secs=90):
        for p in procs:
            p.kill()
        pytest.fail("Diagnose agent failed to start")

    # 3. mainagent (test_server)
    main_proc = subprocess.Popen(
        ["uv", "run", "python", str(TEST_SERVER), "--port", str(MAIN_PORT)],
        env={
            **clean_env,
            "TEMPORAL_ENABLED": "false",
            "INNER_STORAGE_DIR": str(MAINAGENT_DIR / "data" / "inner"),
            "FS_TOOLS_DIR": ".chatagent/fstools",
            "AGENT_FS_DIR": ".chatagent",
            "LOG_DIR": str(MAINAGENT_DIR / "logs"),
            "PROMPTS_DIR": str(MAINAGENT_DIR / "prompts"),
            "USE_NACOS": "FALSE",
            "DIAGNOSE_AGENT_URL": f"http://127.0.0.1:{DIAGNOSE_PORT}",
        },
        cwd=str(MAINAGENT_DIR),
        stdout=open("/tmp/e2e_diag_main.log", "w"),
        stderr=subprocess.STDOUT,
    )
    procs.append(main_proc)
    if not _wait_for_health(f"http://127.0.0.1:{MAIN_PORT}", timeout_secs=90):
        for p in procs:
            p.kill()
        pytest.fail("Main agent failed to start")

    yield f"http://127.0.0.1:{MAIN_PORT}"

    for p in procs:
        p.kill()
        p.wait()


class TestDiagnoseFlow:
    """验证诊断 Agent 完整流程"""

    def test_diagnose_fault_symptom(self, server_url: str) -> None:
        """用户描述故障症状 → mainagent 调 diagnose_agent → 返回诊断结论"""
        import threading

        session_id = f"diag-pw-{os.getpid()}"
        all_events: list[dict] = []
        stream_done = threading.Event()

        def read_sse():
            try:
                with _no_proxy_client(timeout=180) as client:
                    with client.stream("POST", f"{server_url}/chat/stream", json={
                        "session_id": session_id,
                        "message": "我的帕萨特(car_model_id=CAR-001)过减速带咚咚响，帮我诊断一下是什么问题",
                        "user_id": "test-user",
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
                                        all_events.append({"type": et, "data": json.loads(data)})
                                    except:
                                        pass
            except Exception:
                pass
            finally:
                stream_done.set()

        t = threading.Thread(target=read_sse, daemon=True)
        t.start()
        stream_done.wait(timeout=180)

        # 验证 tool 调用
        tool_calls = [
            e["data"].get("data", e["data"]).get("tool_name", "")
            for e in all_events if e["type"] == "tool_call_start"
        ]

        assert "call_diagnose_agent" in tool_calls, \
            f"应调用 call_diagnose_agent，实际: {tool_calls}"

        # 验证有文本响应
        texts = "".join(
            e["data"].get("data", e["data"]).get("content", "")
            for e in all_events if e["type"] == "text"
        )

        # 诊断结果应包含故障相关内容
        has_diagnosis = any(kw in texts for kw in [
            "减震", "悬挂", "刹车", "异响", "故障", "检查",
            "possibilities", "projects", "咚咚",
        ])
        assert has_diagnosis, f"应包含诊断结论，实际: {texts[:300]}"

    def test_diagnose_logs_complete(self, server_url: str) -> None:
        """验证诊断日志链路完整"""
        time.sleep(1)
        log = Path("/tmp/e2e_diag_agent.log").read_text()

        # diagnose agent 应有完整的 tool + HTTP 链路
        assert "[TOOL_START] search_fault_symptoms" in log, "应有 TOOL_START 日志"
        assert "[HTTP_REQ] POST" in log, "应有 HTTP_REQ 日志"
        assert "[HTTP_RES] status=200" in log, "应有 HTTP_RES 日志"
        assert "[TOOL_END] search_fault_symptoms OK" in log, "应有 TOOL_END 日志"

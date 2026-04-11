"""Orchestrator + update_session_state 工具的集成测试。

目标：**不用 mock**，直接验证 chatagent 的 update_session_state 工具在 orchestrator
编排模式下能正确推进真 Temporal workflow 的状态。

测试架构：
    pytest 进程
    ├── 子进程：orchestrator server.py (uv run)
    │          ├── FastAPI listening on :8201
    │          ├── Temporal Worker 跑 GenericWorkflow
    │          └── 读写真 MySQL
    ├── Fake Agent HTTP server（本进程启动）
    │          └── 被 orchestrator 的 call_agent_activity fire-and-forget 调用
    └── Test body:
        1. POST orchestrator /chat/stream/async 启一个 insurance workflow
        2. 等 workflow 初始化，fake agent 被 activity 调到
        3. 构建 AgentDeps(workflow_id=...) + 调 update_session_state 工具
        4. 验证工具返回 "ok"，Temporal 上的 workflow 推进到 propose_quotes

前置：
- MySQL @127.0.0.1:3306 (root/root)
- Redis @127.0.0.1:6379
- Temporal @127.0.0.1:7233
- BMA @127.0.0.1:8103（真 BMA 用 BMA_FORCE_SCENARIO=insurance 绕过，保证稳定）
- orchestrator 项目在兄弟目录 ../com.celiang.hlsc.service.ai.orchestrator
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Request

pytestmark = pytest.mark.asyncio


# ── 路径常量 ──────────────────────────────────────────────

_CHATAGENT_DIR: Path = Path(__file__).resolve().parent.parent
_ORCHESTRATOR_DIR: Path = _CHATAGENT_DIR.parent / "com.celiang.hlsc.service.ai.orchestrator"

# orchestrator 启动端口（和用户可能在跑的 :8101 错开）
_ORCH_PORT: int = 8201
_ORCH_URL: str = f"http://127.0.0.1:{_ORCH_PORT}"


# ── 前置检查 ──────────────────────────────────────────────


def _tcp_ok(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _skip_if_missing(host: str, port: int, name: str) -> None:
    if not _tcp_ok(host, port):
        pytest.skip(f"需要 {name}（{host}:{port}）才能跑此测试。")


@pytest.fixture(scope="session", autouse=True)
def _check_infra() -> None:
    _skip_if_missing("127.0.0.1", 3306, "MySQL")
    _skip_if_missing("127.0.0.1", 6379, "Redis")
    _skip_if_missing("127.0.0.1", 7233, "Temporal")
    if not _ORCHESTRATOR_DIR.exists():
        pytest.skip(f"orchestrator 项目目录不存在: {_ORCHESTRATOR_DIR}")


# ── Fake Agent Server（让 orchestrator 的 call_agent_activity 有地方可调）──
#
# 这个 fake 不会做任何 update_session_state 调用。它只是让 workflow 从
# "刚启动" 推进到 "等下一条用户消息" 的状态。真正的 update_session_state
# 调用由 test body 直接调工具发起。


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PassiveFakeAgent:
    """被动 fake：被 activity 调用后立刻发 callback，不做任何业务动作。"""

    def __init__(self) -> None:
        self.received_payloads: list[dict[str, Any]] = []

    def build_app(self) -> FastAPI:
        app: FastAPI = FastAPI()

        @app.post("/chat/stream/async")
        async def chat_stream_async(request: Request) -> dict[str, str]:
            payload: dict[str, Any] = await request.json()
            self.received_payloads.append(payload)
            callback_url: str = payload.get("callback_url") or ""
            request_id: str = payload["request_id"]
            if callback_url:
                async def _callback() -> None:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(callback_url, json={
                            "request_id": request_id,
                            "status": "success",
                            "error_message": None,
                            "completed_at": int(time.time()),
                        })
                asyncio.create_task(_callback())
            return {"status": "accepted", "request_id": request_id}

        @app.post("/chat/stop")
        async def chat_stop(request: Request) -> dict[str, str]:
            return {"status": "stopped"}

        return app


# ── Orchestrator 子进程 ─────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def orchestrator_subprocess() -> AsyncIterator[dict[str, Any]]:
    """启动真的 orchestrator 子进程，把 fake agent 暴露在另一个端口。"""
    agent_port: int = _free_port()
    fake_agent: PassiveFakeAgent = PassiveFakeAgent()
    agent_app: FastAPI = fake_agent.build_app()
    agent_config: uvicorn.Config = uvicorn.Config(
        agent_app, host="127.0.0.1", port=agent_port, log_level="warning",
    )
    agent_server: uvicorn.Server = uvicorn.Server(agent_config)
    agent_task: asyncio.Task = asyncio.create_task(agent_server.serve())

    # 等 fake agent 就绪
    for _ in range(50):
        if _tcp_ok("127.0.0.1", agent_port):
            break
        await asyncio.sleep(0.05)
    assert _tcp_ok("127.0.0.1", agent_port), "fake agent 启动失败"

    # 启动 orchestrator 子进程
    env: dict[str, str] = os.environ.copy()
    env["SERVER_PORT"] = str(_ORCH_PORT)
    env["AGENT_SERVICE_URL"] = f"http://127.0.0.1:{agent_port}"
    env["ORCHESTRATOR_URL"] = _ORCH_URL
    env["BMA_FORCE_SCENARIO"] = "insurance"
    env["CLEANUP_INTERVAL_SECONDS"] = "60"

    proc: subprocess.Popen = subprocess.Popen(
        ["uv", "run", "python", "server.py"],
        cwd=str(_ORCHESTRATOR_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # 等 orchestrator 起来（health check）
    deadline: float = time.time() + 30.0
    ready: bool = False
    while time.time() < deadline:
        if _tcp_ok("127.0.0.1", _ORCH_PORT):
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    r = await client.get(f"{_ORCH_URL}/health")
                    if r.status_code == 200:
                        ready = True
                        break
            except Exception:
                pass
        await asyncio.sleep(0.3)

    if not ready:
        # 拿子进程输出帮助调试
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output = b""
        pytest.fail(
            f"orchestrator 30s 内未就绪。stdout/stderr:\n"
            f"{output.decode(errors='replace')[-3000:]}"
        )

    try:
        yield {
            "orch_url": _ORCH_URL,
            "fake_agent": fake_agent,
            "orch_proc": proc,
        }
    finally:
        # Teardown orchestrator
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        # Teardown fake agent
        agent_server.should_exit = True
        await asyncio.sleep(0.1)
        agent_task.cancel()
        try:
            await agent_task
        except (asyncio.CancelledError, Exception):
            pass


# ── 测试辅助 ─────────────────────────────────────────────


async def _start_insurance_workflow(
    orch_url: str, user_id: str, session_id: str,
) -> str:
    """通过 POST /chat/stream/async 启一个 insurance workflow，返回 workflow_id。

    借助被动 fake agent，第一次消息进来后 workflow 初始化完成 + 第一次 activity
    被 fire-and-forget 调用 + fake agent 立即 callback success → turn_tasks 进入
    success 状态。

    workflow_id 从 response 不直接拿，改为从 active workflow 列表推断：
    格式 `insurance:{user_id}:{session_id}:{uuid}`，所以只需要监听 Temporal 里该
    前缀的活跃 workflow 即可。
    """
    from temporalio.client import Client as _TemporalClient

    request_id: str = f"init_{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{orch_url}/chat/stream/async",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "request_id": request_id,
                "message": "我想买车险",
            },
        )
    assert r.status_code == 200, r.text

    # 通过 Temporal list workflows 找刚才创建的 workflow
    temporal_client: _TemporalClient = await _TemporalClient.connect("127.0.0.1:7233")
    deadline: float = time.time() + 15.0
    prefix: str = f"insurance:{user_id}:{session_id}:"
    while time.time() < deadline:
        # Temporal list_workflows 支持 query 语法，按 WorkflowType + 时间过滤
        async for wf_info in temporal_client.list_workflows(
            f"WorkflowType = 'GenericWorkflow' AND ExecutionStatus = 'Running'"
        ):
            if wf_info.id.startswith(prefix):
                return wf_info.id
        await asyncio.sleep(0.3)

    raise AssertionError(f"15s 内没找到前缀为 {prefix} 的活跃 workflow")


# ── 测试用例 ─────────────────────────────────────────────


async def test_update_session_state_tool_advances_workflow(
    orchestrator_subprocess: dict[str, Any],
) -> None:
    """核心测试：真 chatagent 工具 → 真 orchestrator → 真 Temporal workflow."""
    orch_url: str = orchestrator_subprocess["orch_url"]

    user_id: str = f"tool_test_{uuid.uuid4().hex[:8]}"
    session_id: str = f"sess_{uuid.uuid4().hex[:8]}"

    # Step 1: 启 insurance workflow
    workflow_id: str = await _start_insurance_workflow(orch_url, user_id, session_id)
    assert workflow_id.startswith("insurance:")

    # Step 2: 模拟 Agent.run() 内部，构建一个 AgentDeps 直接调 update_session_state 工具
    from pydantic_ai import RunContext

    from agent_sdk._agent.deps import AgentDeps
    from hlsc.tools.update_session_state import update_session_state

    deps: AgentDeps = AgentDeps(
        session_id=session_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        # orchestrator 字段
        workflow_id=workflow_id,
        orchestrator_url=orch_url,
        current_step_detail={
            "id": "collect_info",
            "name": "收集投保车辆与需求",
            "goal": "拿到 VIN / 注册时间 / 需求 / 目标返现",
            "success_criteria": "四项字段齐",
            "expected_fields": [
                {"name": "vin", "type": "str"},
                {"name": "register_date", "type": "str"},
                {"name": "needs_description", "type": "str"},
                {"name": "target_cashback", "type": "float"},
            ],
            "allowed_next": ["propose_quotes"],
            "skip_hint": None,
            "repeatable": True,
        },
        step_pending_fields=["vin", "register_date", "needs_description", "target_cashback"],
    )

    # 构造 RunContext — pydantic_ai 的 RunContext 只在 model/run 时使用，这里我们
    # 只需要它的 .deps 字段。用一个极简 Stub。
    class _Ctx:
        def __init__(self, deps_obj: AgentDeps) -> None:
            self.deps: AgentDeps = deps_obj

    ctx: Any = _Ctx(deps)  # type: ignore[assignment]

    # Step 3: 调工具 —— 本轮收齐 4 个字段 + advance_to=propose_quotes
    result: str = await update_session_state(
        ctx,
        updates={
            "vin": "LHGK12345ABC67890",
            "register_date": "2020-06-15",
            "needs_description": "想买基础车险，主险 + 不计免赔",
            "target_cashback": 3000.0,
        },
        advance_to="propose_quotes",
    )

    # 断言：工具返回 ok
    assert result == "ok", f"工具返回应为 ok，实际 {result}"

    # 断言：同 turn 单次推进守卫已被触发
    assert deps._step_mutation_committed is True

    # 断言：本地 session_state 也同步刷新了（方便 LLM 后续工具调用看最新值）
    assert deps.session_state["vin"] == "LHGK12345ABC67890"
    assert deps.session_state["target_cashback"] == 3000.0

    # 断言：Temporal workflow 推进到 propose_quotes（用 temporal client query）
    from temporalio.client import Client
    client = await Client.connect("127.0.0.1:7233")
    handle = client.get_workflow_handle(workflow_id)
    current: str = await handle.query("get_current_step")
    completed: list[str] = await handle.query("get_completed_steps")
    assert current == "propose_quotes", f"current_step={current}"
    assert completed == ["collect_info"], f"completed={completed}"


async def test_update_session_state_tool_missing_fields_returns_error(
    orchestrator_subprocess: dict[str, Any],
) -> None:
    """本地预校验：只写一半字段就 advance 应该被工具本地拒绝。"""
    orch_url: str = orchestrator_subprocess["orch_url"]
    user_id: str = f"tool_test_{uuid.uuid4().hex[:8]}"
    session_id: str = f"sess_{uuid.uuid4().hex[:8]}"

    workflow_id: str = await _start_insurance_workflow(orch_url, user_id, session_id)

    from agent_sdk._agent.deps import AgentDeps
    from hlsc.tools.update_session_state import update_session_state

    deps: AgentDeps = AgentDeps(
        session_id=session_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        workflow_id=workflow_id,
        orchestrator_url=orch_url,
        current_step_detail={
            "id": "collect_info",
            "name": "收集",
            "goal": "...",
            "success_criteria": "...",
            "expected_fields": [
                {"name": "vin", "type": "str"},
                {"name": "register_date", "type": "str"},
                {"name": "needs_description", "type": "str"},
                {"name": "target_cashback", "type": "float"},
            ],
            "allowed_next": ["propose_quotes"],
            "skip_hint": None,
            "repeatable": True,
        },
        step_pending_fields=[
            "vin", "register_date", "needs_description", "target_cashback",
        ],
    )

    class _Ctx:
        def __init__(self, deps_obj: AgentDeps) -> None:
            self.deps = deps_obj

    ctx: Any = _Ctx(deps)

    # 只写 2 个字段，然后 advance → 本地预校验应该拦住
    result: str = await update_session_state(
        ctx,
        updates={"vin": "LHG...", "register_date": "2020-01-01"},
        advance_to="propose_quotes",
    )
    assert result.startswith("missing_fields:"), (
        f"预期 missing_fields，实际 {result}"
    )
    # 应该包含缺的两个字段
    assert "needs_description" in result
    assert "target_cashback" in result

    # 守卫没被触发（因为本轮没推进成功）
    assert deps._step_mutation_committed is False
    # 本地 session_state 也不应该被污染（本地预校验在写之前就返回）
    assert "vin" not in deps.session_state

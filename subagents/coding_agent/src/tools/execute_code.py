"""QueryCodingAgent 代码执行工具。"""

from __future__ import annotations

import shlex
import sys

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import K8sExecutor, get_executor
from src.coding_context import resolve_code_dir


async def execute_code(
    ctx: RunContext[AgentDeps],
    main_py_path: str,
) -> str:
    """执行当前 code_dir 中的 main.py。"""
    code_dir = resolve_code_dir(ctx.deps.request_context)
    if not code_dir:
        return "[执行失败] 缺少 code_dir 上下文"

    if not main_py_path:
        return "[执行失败] main_py_path 不能为空"

    normalized_path = main_py_path if main_py_path.startswith("/") else f"{code_dir}/{main_py_path}"
    normalized_path = normalized_path.replace("\\", "/")
    expected_path = f"{code_dir.rstrip('/')}/main.py"
    if normalized_path != expected_path:
        return f"[执行失败] 当前只允许执行 {expected_path}"

    backend = ctx.deps.fs_tools_backend
    if backend is None or not hasattr(backend, "_resolve_path"):
        return "[执行失败] 当前执行环境不支持读取脚本文件"

    resolved_path = backend._resolve_path(normalized_path)  # type: ignore[attr-defined]
    if not resolved_path.exists():
        return f"[执行失败] 文件不存在：{normalized_path}"

    code = resolved_path.read_text(encoding="utf-8")
    executor = get_executor()

    if isinstance(executor, K8sExecutor):
        # k8s 模式：直接传入代码字符串执行
        command = f"python3 -c {shlex.quote(code)}"
    else:
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(resolved_path))}"

    # 传递必要环境变量到执行环境（k8s Pod 不继承 host 环境）
    import os
    exec_env: dict[str, str] = {"PYTHONIOENCODING": "utf-8"}
    api_base = os.getenv("API_BASE_URL")
    if api_base:
        exec_env["API_BASE_URL"] = api_base

    result = await executor.execute(
        command,
        timeout=30,
        env=exec_env,
        cwd=str(resolved_path.parent) if not isinstance(executor, K8sExecutor) else None,
    )

    if not result.success:
        return f"[执行失败] 退出码 {result.exit_code}\n{result.output}".strip()

    if not result.stdout:
        return "[执行成功] 无输出"

    return result.stdout


def create_code_agent_tool_map() -> dict:
    """创建 QueryCodingAgent 工具映射。"""
    return {
        "execute_code": execute_code,
    }

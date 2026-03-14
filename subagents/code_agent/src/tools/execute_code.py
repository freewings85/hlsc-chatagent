"""CodeAgent 代码执行工具。

通过 SDK 的 CodeExecutor 抽象层执行，支持 local / k8s 模式。
- local：写入临时文件后执行
- k8s：通过 python3 -c 传入代码（不依赖文件系统共享）
"""

from __future__ import annotations

import shlex
from pathlib import Path

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import K8sExecutor, get_executor

_CODE_DIR = Path("/tmp/code_agent")


async def execute_code(
    ctx: RunContext[AgentDeps],
    code: str,
    filename: str = "query.py",
) -> str:
    """Execute a Python script to query business APIs.

    Write the code as a complete Python script. The script should use httpx
    to call business APIs and print the results.

    Environment variable API_BASE_URL is available for the API base URL.

    Args:
        code: Complete Python script content.
        filename: Script filename (default: query.py).

    Returns:
        Script stdout output, or error message if execution failed.
    """
    executor = get_executor()

    if isinstance(executor, K8sExecutor):
        # k8s 模式：通过 python3 -c 直接传入代码（Pod 里没有本地文件）
        command = f"python3 -c {shlex.quote(code)}"
    else:
        # local 模式：写入临时文件后执行
        _CODE_DIR.mkdir(parents=True, exist_ok=True)
        script_path = _CODE_DIR / filename
        script_path.write_text(code, encoding="utf-8")
        command = f"python3 {script_path}"

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
    )

    if not result.success:
        return f"[执行失败] 退出码 {result.exit_code}\n{result.output}".strip()

    if not result.stdout:
        return "[执行成功] 无输出"

    return result.stdout


def create_code_agent_tool_map() -> dict:
    """创建 CodeAgent 工具映射。"""
    return {
        "execute_code": execute_code,
    }

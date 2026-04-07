"""QueryCodingAgent Python 执行工具。"""

from __future__ import annotations

import shlex
import sys

from pydantic_ai import RunContext
from pydantic import Field
from typing import Annotated

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import get_executor


async def run_python(
    ctx: RunContext[AgentDeps],
    code: Annotated[str, Field(description="he python code to execute to do further analysis or calculation.")],
) -> str:
    """Execute Python code for analysis, querying, or calculation.

    If you want the user to see a value, print it with `print(...)`.
    Only printed stdout is visible to the user.
    """
    if not code or not code.strip():
        return "[执行失败] code 不能为空"

    executor = get_executor()
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    exec_env: dict[str, str] = {"PYTHONIOENCODING": "utf-8"}

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
    """创建 QueryCodingAgent 工具映射。"""
    return {
        "run_python": run_python,
    }

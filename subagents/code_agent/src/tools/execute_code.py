"""CodeAgent 代码执行工具。

通过 SDK 的 CodeExecutor 抽象层执行，支持 local / k8s 模式。
先将代码写入临时文件，再通过 executor 执行 python3 脚本。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import get_executor

# 代码写入目录（local 模式用，k8s 模式脚本通过 stdin 传入）
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
    # 写入临时文件
    _CODE_DIR.mkdir(parents=True, exist_ok=True)
    script_path = _CODE_DIR / filename
    script_path.write_text(code, encoding="utf-8")

    executor = get_executor()
    result = await executor.execute(
        f"python3 {script_path}",
        timeout=30,
        env={"PYTHONIOENCODING": "utf-8"},
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

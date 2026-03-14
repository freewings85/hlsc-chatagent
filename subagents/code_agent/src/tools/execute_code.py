"""CodeAgent 代码执行工具。

当前实现：本地 bash 执行 Python 脚本。
未来可扩展：K8s Job、Docker sandbox、远程执行等。

扩展方式：
  1. 新增 executor 实现（如 k8s_executor.py）
  2. 通过环境变量 CODE_EXECUTOR_TYPE 选择执行器
  3. execute_code 内部路由到对应实现
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps

# 代码执行目录
_CODE_DIR = Path("/tmp/code_agent")

# 执行器类型（预留扩展点）
_EXECUTOR_TYPE = os.getenv("CODE_EXECUTOR_TYPE", "local")


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
    if _EXECUTOR_TYPE == "local":
        return await _execute_local(code, filename)
    # 未来扩展点：
    # elif _EXECUTOR_TYPE == "k8s":
    #     return await _execute_k8s(code, filename)
    # elif _EXECUTOR_TYPE == "docker":
    #     return await _execute_docker(code, filename)
    else:
        return f"[错误] 未知的执行器类型: {_EXECUTOR_TYPE}"


async def _execute_local(code: str, filename: str) -> str:
    """本地执行 Python 脚本。"""
    _CODE_DIR.mkdir(parents=True, exist_ok=True)
    script_path = _CODE_DIR / filename
    script_path.write_text(code, encoding="utf-8")

    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()
            return f"[执行失败] 退出码 {result.returncode}\n{error}\n{output}".strip()

        if not output:
            return "[执行成功] 无输出"

        return output

    except subprocess.TimeoutExpired:
        return "[执行超时] 脚本运行超过 30 秒"
    except Exception as exc:
        return f"[执行异常] {exc}"


def create_code_agent_tool_map() -> dict:
    """创建 CodeAgent 工具映射。"""
    return {
        "execute_code": execute_code,
    }

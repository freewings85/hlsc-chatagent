"""Bash 工具：在 shell 中执行命令。

设计参考 Claude Code Bash 工具：
- 使用 asyncio.create_subprocess_shell 异步执行
- 超时保护（默认 120s，最大 600s）
- 输出截断（MAX_OUTPUT_BYTES = 30KB）
- 合并 stdout + stderr，非零退出码时在结果前标注 [exit N]
"""

import asyncio

from pydantic_ai import RunContext

from src.agent.deps import AgentDeps

MAX_OUTPUT_BYTES = 30_000
MAX_TIMEOUT_SECONDS = 600


async def bash(
    ctx: RunContext[AgentDeps],
    command: str,
    timeout: int = 120,
) -> str:
    """在 shell 中执行命令，返回输出结果。

    Args:
        command: 要执行的 shell 命令。
        timeout: 超时秒数（默认 120，最大 600）。

    Returns:
        命令输出（stdout + stderr），超时或非零退出码时附带说明。
    """
    effective_timeout = min(timeout, MAX_TIMEOUT_SECONDS)

    # bash 在 backend 根目录下执行，与 write/read/edit 保持一致
    cwd: str | None = None
    backend = ctx.deps.backend
    if backend is not None and hasattr(backend, "cwd"):
        cwd = str(backend.cwd)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except OSError as e:
        return f"命令启动失败：{e}"

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=effective_timeout
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return f"命令超时（{effective_timeout}s）：{command}"

    out = stdout_bytes.decode(errors="replace")
    err = stderr_bytes.decode(errors="replace")

    combined = out
    if err:
        combined = combined + f"\n[stderr]\n{err}" if combined else err

    # 超出限制时截断
    if len(combined.encode()) > MAX_OUTPUT_BYTES:
        combined = combined.encode()[:MAX_OUTPUT_BYTES].decode(errors="replace")
        combined += f"\n...[输出截断，超过 {MAX_OUTPUT_BYTES} 字节]"

    if proc.returncode != 0:
        return f"[exit {proc.returncode}]\n{combined}"

    return combined

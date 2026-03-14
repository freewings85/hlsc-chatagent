"""Bash 工具：在 shell 中执行命令。

执行环境由 CODE_EXECUTOR 环境变量控制（local / k8s）。
"""

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps

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
    from agent_sdk._agent.executor import get_executor
    from agent_sdk._config.settings import get_fs_config

    effective_timeout = min(timeout, MAX_TIMEOUT_SECONDS)

    # bash 工作目录
    cwd: str | None = get_fs_config().bash_cwd

    # skill 环境变量
    env: dict[str, str] | None = None
    if ctx.deps.skill_env:
        env = dict(ctx.deps.skill_env)

    executor = get_executor()
    result = await executor.execute(command, timeout=effective_timeout, cwd=cwd, env=env)

    combined = result.output

    # 超出限制时截断
    if len(combined.encode()) > MAX_OUTPUT_BYTES:
        combined = combined.encode()[:MAX_OUTPUT_BYTES].decode(errors="replace")
        combined += f"\n...[输出截断，超过 {MAX_OUTPUT_BYTES} 字节]"

    if not result.success:
        return f"[exit {result.exit_code}]\n{combined}"

    return combined

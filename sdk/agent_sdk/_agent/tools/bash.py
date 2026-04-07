"""Bash 工具：在 shell 中执行命令。

执行环境由 CODE_EXECUTOR 环境变量控制（local / k8s）。

PATH 注入：
  自动将 agent 进程的 Python 所在目录加到 PATH 最前面，
  确保 bash 里的 `python` 命令使用和 agent 相同的 Python 环境。
  可通过 BASH_EXTRA_PATH 追加额外路径（多个用 : 或 ; 分隔）。
"""

import os
import sys
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps

MAX_OUTPUT_BYTES = 30_000
MAX_TIMEOUT_SECONDS = 600

_OTEL_BOOT: str = str(Path(__file__).parent / "_otel_boot.py")


def _build_path_env() -> str:
    """构建 bash 执行时的 PATH。

    优先级：sys.executable 目录 > BASH_EXTRA_PATH > 原始 PATH
    """
    parts: list[str] = []

    # agent 进程的 Python 所在目录（始终最高优先级）
    python_bin_dir = os.path.dirname(sys.executable)
    if python_bin_dir:
        parts.append(python_bin_dir)

    # 可选的额外路径
    extra = os.getenv("BASH_EXTRA_PATH", "")
    if extra:
        parts.append(extra)

    # 原始 PATH
    original = os.environ.get("PATH", "")
    if original:
        parts.append(original)

    return os.pathsep.join(parts)


async def bash(
    ctx: RunContext[AgentDeps],
    command: str,
    timeout: int = 120,
) -> str:
    """在 shell 中执行命令，返回输出结果。

    当执行 skill 中提到的脚本时，必须使用 <skill-dir> 拼接的绝对路径。
    例如 skill 提到 `scripts/run.py`，<skill-dir> 为 `/app/.chatagent/fstools/skills/my-skill`，
    则 command 应为 `python /app/.chatagent/fstools/skills/my-skill/scripts/run.py`。
    不允许使用相对路径执行脚本。

    Args:
        command: 要执行的 shell 命令。脚本文件必须使用绝对路径。
        timeout: 超时秒数（默认 120，最大 600）。

    Returns:
        命令输出（stdout + stderr），超时或非零退出码时附带说明。
    """
    from agent_sdk._agent.executor import get_executor
    from agent_sdk._config.settings import get_fs_config

    effective_timeout = min(timeout, MAX_TIMEOUT_SECONDS)

    # bash 工作目录
    cwd: str | None = get_fs_config().bash_cwd

    # 环境变量：继承父进程环境 + PATH 注入 + 会话上下文 + UTF-8 + OTel trace
    env: dict[str, str] = {**os.environ, **{
        "PATH": _build_path_env(),
        "PYTHONUTF8": "1",
        "OWNER_ID": ctx.deps.user_id,
        "CONVERSATION_ID": ctx.deps.session_id,
    }}

    # 注入 OTel trace context → 子进程继承当前 span 作为 parent
    from opentelemetry.propagate import inject
    from opentelemetry.context import get_current
    inject(env, context=get_current())

    # python 命令自动注入 OTel bootstrap（instrument httpx + 恢复 trace context）
    if env.get("LOGFIRE_ENDPOINT") and command.lstrip().startswith("python "):
        command = command.replace("python ", f"python {_OTEL_BOOT} ", 1)

    # 中断回调：脚本输出 __INTERRUPT__:{json} 时触发
    async def _on_interrupt(data: dict[str, Any]) -> str:
        from agent_sdk._agent.tools.call_interrupt import call_interrupt
        return await call_interrupt(ctx, data)

    executor = get_executor()
    result = await executor.execute_interactive(
        command, timeout=effective_timeout, cwd=cwd, env=env, on_interrupt=_on_interrupt,
    )

    combined = result.output

    # 超出限制时截断
    if len(combined.encode()) > MAX_OUTPUT_BYTES:
        combined = combined.encode()[:MAX_OUTPUT_BYTES].decode(errors="replace")
        combined += f"\n...[输出截断，超过 {MAX_OUTPUT_BYTES} 字节]"

    if not result.success:
        return f"[exit {result.exit_code}]\n{combined}"

    return combined

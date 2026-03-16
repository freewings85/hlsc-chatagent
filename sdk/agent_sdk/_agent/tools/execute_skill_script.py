"""execute_skill_script 工具：执行 skill 目录下的脚本。

只允许执行 {AGENT_FS_DIR}/fstools/skills/{skill_name}/scripts/ 下的脚本，
不能执行任意命令。安全替代通用 bash 工具。

Python 环境配置：
  SKILL_PYTHON 环境变量指定 Python 解释器路径。
  不设则使用当前 agent 进程的 Python（sys.executable）。

  示例：
    SKILL_PYTHON=python          # Windows 默认
    SKILL_PYTHON=python3         # Linux 默认
    SKILL_PYTHON=/path/to/.venv/bin/python  # 指定 venv
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import get_executor
from agent_sdk.logging import log_tool_start, log_tool_end


def _get_python() -> str:
    """获取 Python 解释器路径。

    优先级：SKILL_PYTHON 环境变量 > sys.executable
    """
    env_python = os.getenv("SKILL_PYTHON")
    if env_python:
        return env_python
    # 使用当前进程的 Python（跨平台，一定存在）
    return sys.executable


def _build_command(full_path: Path, args: str) -> str:
    """根据文件类型和平台构建执行命令。"""
    suffix = full_path.suffix
    # 路径加引号，防止空格等特殊字符问题
    quoted_path = f'"{full_path}"'

    if suffix == ".py":
        python = _get_python()
        return f'{python} {quoted_path} {args}'.strip()
    elif suffix == ".sh":
        if platform.system() == "Windows":
            # Windows 上尝试用 Git Bash 或 WSL
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            if git_bash.exists():
                return f'"{git_bash}" {quoted_path} {args}'.strip()
            # 回退：用 PowerShell 执行（可能不兼容）
            return f'powershell -File {quoted_path} {args}'.strip()
        return f'bash {quoted_path} {args}'.strip()
    elif suffix == ".ps1":
        return f'powershell -ExecutionPolicy Bypass -File {quoted_path} {args}'.strip()
    elif suffix == ".bat" or suffix == ".cmd":
        return f'cmd /c {quoted_path} {args}'.strip()
    else:
        return f'{quoted_path} {args}'.strip()


async def execute_skill_script(
    ctx: RunContext[AgentDeps],
    skill_name: Annotated[str, Field(description="skill 名称，如 'query-part-price'")],
    script_path: Annotated[str, Field(description="脚本在 skill 目录下的相对路径，如 'scripts/search_parts.py'")],
    args: Annotated[str, Field(description="传给脚本的参数")] = "",
) -> str:
    """执行指定 skill 目录下的脚本。

    只能执行 skills/{skill_name}/ 目录下的脚本文件，不能执行任意命令。
    脚本路径必须是相对于 skill 目录的路径（如 scripts/query.py）。
    """
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("execute_skill_script", sid, rid, {
        "skill_name": skill_name, "script_path": script_path,
    })

    try:
        from agent_sdk._config.settings import get_fs_config
        config = get_fs_config()

        # 构建脚本绝对路径
        skills_root = Path(config.agent_fs_dir) / "fstools" / "skills"
        full_path = (skills_root / skill_name / script_path).resolve()

        # 安全检查：路径必须在 skills_root 内
        try:
            full_path.relative_to(skills_root.resolve())
        except ValueError:
            log_tool_end("execute_skill_script", sid, rid, exc=ValueError("路径越界"))
            return "Error: 脚本路径不在 skills 目录内"

        if not full_path.exists():
            log_tool_end("execute_skill_script", sid, rid, exc=FileNotFoundError(str(full_path)))
            return f"Error: 脚本不存在: {script_path}"

        if not full_path.is_file():
            log_tool_end("execute_skill_script", sid, rid, exc=ValueError("不是文件"))
            return f"Error: {script_path} 不是文件"

        command = _build_command(full_path, args)

        executor = get_executor()
        result = await executor.execute(
            command,
            timeout=30,
            cwd=str(full_path.parent),
            env={"PYTHONIOENCODING": "utf-8"},
        )

        if not result.success:
            log_tool_end("execute_skill_script", sid, rid, exc=RuntimeError(result.output))
            return f"[脚本执行失败] 退出码 {result.exit_code}\n{result.output}"

        log_tool_end("execute_skill_script", sid, rid, {"exit_code": 0})
        return result.stdout if result.stdout else "[执行成功] 无输出"

    except Exception as e:
        log_tool_end("execute_skill_script", sid, rid, exc=e)
        return f"Error: execute_skill_script failed - {e}"

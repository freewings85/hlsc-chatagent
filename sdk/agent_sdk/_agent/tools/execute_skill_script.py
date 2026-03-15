"""execute_skill_script 工具：执行 skill 目录下的脚本。

只允许执行 {AGENT_FS_DIR}/fstools/skills/{skill_name}/scripts/ 下的脚本，
不能执行任意命令。安全替代通用 bash 工具。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.executor import get_executor
from agent_sdk.logging import log_tool_start, log_tool_end


async def execute_skill_script(
    ctx: RunContext[AgentDeps],
    skill_name: Annotated[str, Field(description="skill 名称，如 'confirm-car-info'")],
    script_path: Annotated[str, Field(description="脚本在 skill 目录下的相对路径，如 'scripts/query.py'")],
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
            return f"Error: 脚本路径不在 skills 目录内"

        if not full_path.exists():
            log_tool_end("execute_skill_script", sid, rid, exc=FileNotFoundError(str(full_path)))
            return f"Error: 脚本不存在: {script_path}"

        if not full_path.is_file():
            log_tool_end("execute_skill_script", sid, rid, exc=ValueError("不是文件"))
            return f"Error: {script_path} 不是文件"

        # 根据文件类型选择执行命令
        suffix = full_path.suffix
        if suffix == ".py":
            command = f"python3 {full_path} {args}".strip()
        elif suffix == ".sh":
            command = f"bash {full_path} {args}".strip()
        else:
            command = f"{full_path} {args}".strip()

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

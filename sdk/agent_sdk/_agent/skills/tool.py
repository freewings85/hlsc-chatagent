"""invoke_skill：Pydantic AI tool，激活 skill 并持久化。

设计依据（Decision 1）：
- LLM 通过工具调用触发 skill（hard constraint，不可忽略）
- 工具调用结构上先于文字生成，确保 skill 指令一定被加载
- SKILL.md 内容存入 InvokedSkillStore（session 级持久化），compact 后仍可注入

两种 skill 类型：
- Prompt 型（SKILL.md only）：返回 markdown 指令给 LLM
- Script 型（SKILL.md + script.py）：执行 Python 脚本，复用 call_interrupt 中断

工具会注册到 deps.tool_map["Skill"]，通过 DynamicToolset 动态提供。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.skills.invoked_store import InvokedSkill

logger: logging.Logger = logging.getLogger(__name__)


async def invoke_skill(ctx: RunContext[AgentDeps], skill: str, args: str = "") -> str:
    """Execute a skill within the main session.

    When users ask you to perform tasks, check if any of the available skills
    match. Skills provide specialized capabilities and domain knowledge.

    When users reference a slash command or "/<something>" (e.g., "/commit",
    "/review-pr"), they are referring to a skill. Use this tool to invoke it.

    IMPORTANT: When a skill matches the user's request, this is a BLOCKING
    REQUIREMENT — invoke this tool BEFORE generating any other response.

    Available skills are listed in system-reminder messages in the session.

    Args:
        skill: The skill name to invoke (e.g., "commit", "review-pr").
        args:  Optional arguments or hints passed to the skill.
    """
    registry = ctx.deps.skill_registry
    if registry is None:
        return "[skill system not available]"

    entry = registry.get(skill)
    if entry is None:
        available = ", ".join(e.name for e in registry.list_invocable())
        return f"[skill not found: '{skill}'. Available: {available or 'none'}]"

    # ── Script 型 skill：执行 Python 脚本 ──
    if entry.script_class is not None:
        return await _execute_script_skill(ctx, skill, args, entry)

    # ── Prompt 型 skill：返回 markdown 指令 ──
    return await _execute_prompt_skill(ctx, skill, args, entry)


async def _execute_script_skill(
    ctx: RunContext[AgentDeps],
    skill: str,
    args: str,
    entry: object,
) -> str:
    """执行 Script 型 skill（Python 脚本，interrupt 复用 call_interrupt）。"""
    from agent_sdk._agent.skills.script_executor import execute_skill_script

    script = entry.script_class()  # type: ignore[union-attr]
    logger.info("执行 Script 型 skill: %s", skill)
    output: str = await execute_skill_script(script, ctx)
    return output or "[skill script completed]"


async def _execute_prompt_skill(
    ctx: RunContext[AgentDeps],
    skill: str,
    args: str,
    entry: object,
) -> str:
    """执行 Prompt 型 skill（返回 SKILL.md markdown）。"""
    # 持久化到 session 文件
    store = ctx.deps.invoked_skill_store
    if store is not None:
        await store.record(InvokedSkill(
            name=skill,
            content=entry.content,  # type: ignore[union-attr]
            invoked_at=datetime.now(timezone.utc),
        ))

    content: str = entry.content  # type: ignore[union-attr]
    skill_dir_hint: str = ""
    if entry.source_path is not None:  # type: ignore[union-attr]
        skill_dir_path: Path = entry.source_path.parent.resolve()  # type: ignore[union-attr]
        skill_dir: str = str(skill_dir_path)
        skill_dir_hint = f"\n\n<skill-dir>{skill_dir}</skill-dir>"

        # 计算 fs 工具（read/glob/grep）可用的虚拟路径
        backend = ctx.deps.fs_tools_backend
        if backend is not None and hasattr(backend, "cwd"):
            try:
                rel: Path = skill_dir_path.relative_to(backend.cwd)
                skill_dir_hint += f"\n<skill-fs-dir>/{rel}</skill-fs-dir>"
            except ValueError:
                pass

    # metadata tag（参照 Claude Code nI8()）
    metadata_tag: str = (
        f"<command-name>{skill}</command-name>"
        f"<command-args>{args}</command-args>"
        f"<skill-format>true</skill-format>"
    )
    execution_hint: str = (
        "\n\n<execution-hint>"
        "立即按上述步骤调用工具执行。不要输出文字向用户确认或解释。"
        "能从上下文推断的参数直接用。"
        "</execution-hint>"
    )
    return f"{metadata_tag}{skill_dir_hint}\n\n{content}{execution_hint}"

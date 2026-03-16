"""invoke_skill：Pydantic AI tool，激活 skill 并持久化。

设计依据（Decision 1）：
- LLM 通过工具调用触发 skill（hard constraint，不可忽略）
- 工具调用结构上先于文字生成，确保 skill 指令一定被加载
- SKILL.md 内容存入 InvokedSkillStore（session 级持久化），compact 后仍可注入

工具会注册到 deps.tool_map["Skill"]，通过 DynamicToolset 动态提供。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.skills.invoked_store import InvokedSkill


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

    # 持久化到 session 文件
    store = ctx.deps.invoked_skill_store
    if store is not None:
        await store.record(InvokedSkill(
            name=skill,
            content=entry.content,
            invoked_at=datetime.now(timezone.utc),
        ))

    content = entry.content
    skill_dir_hint = ""
    if entry.source_path is not None:
        skill_dir = entry.source_path.parent.resolve()
        skill_dir_hint = f"\n\n<skill-dir>{skill_dir}</skill-dir>"

    # metadata tag（参照 Claude Code nI8()）
    metadata_tag = (
        f"<command-name>{skill}</command-name>"
        f"<command-args>{args}</command-args>"
        f"<skill-format>true</skill-format>"
    )
    execution_hint = (
        "\n\n<execution-hint>"
        "立即按上述步骤调用工具执行。不要输出文字向用户确认或解释。"
        "能从上下文推断的参数直接用。"
        "当 skill 提到脚本文件时，使用 skill-dir 中的路径拼接完整绝对路径。"
        "</execution-hint>"
    )
    return f"{metadata_tag}{skill_dir_hint}\n\n{content}{execution_hint}"

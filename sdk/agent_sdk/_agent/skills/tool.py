"""invoke_skill：Pydantic AI tool，激活 skill 并持久化。

设计：
- 每个 skill 都可以同时拥有 SKILL.md（描述/指令）和 scripts/（可执行脚本）
- invoke_skill("skill_name") → 返回 SKILL.md 指令给 LLM
- invoke_skill("skill_name:script_name", args='{...}') → 执行 scripts/ 下的指定脚本

不区分 prompt 型和 script 型，所有 skill 统一处理。
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
    """Execute a skill or run a skill script.

    Two modes:
    - invoke_skill("skill_name") → load SKILL.md instructions
    - invoke_skill("skill_name:script_name", args='{"key":"value"}') → run a script

    Available skills are listed in system-reminder messages in the session.

    Args:
        skill: Skill name, or "skill_name:script_name" to run a specific script.
        args:  Optional JSON arguments passed to the script (only used in script mode).
    """
    registry = ctx.deps.skill_registry
    if registry is None:
        return "[skill system not available]"

    # ── 解析 skill_name:script_name ──
    if ":" in skill:
        skill_name, script_name = skill.split(":", 1)
        return await _execute_script(ctx, skill_name, script_name, args, registry)

    # ── 载入 SKILL.md 指令 ──
    return await _load_skill_prompt(ctx, skill, args, registry)


async def _load_skill_prompt(
    ctx: RunContext[AgentDeps],
    skill: str,
    args: str,
    registry: object,
) -> str:
    """载入 SKILL.md 内容返回给 LLM，附带可用脚本列表。"""
    entry = registry.get(skill)  # type: ignore[union-attr]
    if entry is None:
        available = ", ".join(e.name for e in registry.list_invocable())  # type: ignore[union-attr]
        return f"[skill not found: '{skill}'. Available: {available or 'none'}]"

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

        backend = ctx.deps.fs_tools_backend
        if backend is not None and hasattr(backend, "cwd"):
            try:
                rel: Path = skill_dir_path.relative_to(backend.cwd)
                skill_dir_hint += f"\n<skill-fs-dir>/{rel}</skill-fs-dir>"
            except ValueError:
                pass

    # 列出可用脚本
    scripts_hint: str = _build_scripts_hint(entry)

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
    return f"{metadata_tag}{skill_dir_hint}\n\n{content}{scripts_hint}{execution_hint}"


async def _execute_script(
    ctx: RunContext[AgentDeps],
    skill_name: str,
    script_name: str,
    args: str,
    registry: object,
) -> str:
    """执行 skill 下指定名称的脚本。"""
    from agent_sdk._agent.skills.script_registry import load_script_class_by_name

    entry = registry.get(skill_name)  # type: ignore[union-attr]
    if entry is None:
        return f"[skill not found: '{skill_name}']"

    if entry.source_path is None:  # type: ignore[union-attr]
        return f"[skill '{skill_name}' has no source path]"

    skill_dir: Path = entry.source_path.parent.resolve()  # type: ignore[union-attr]
    script_class = load_script_class_by_name(skill_dir, script_name)

    if script_class is None:
        return f"[script '{script_name}' not found in skill '{skill_name}']"

    from agent_sdk._agent.skills.script_executor import execute_skill_script

    script = script_class()
    logger.info("执行脚本: %s:%s (args=%s)", skill_name, script_name, args)
    output: str = await execute_skill_script(script, ctx, args=args)
    return output or "[skill script completed]"


def _build_scripts_hint(entry: object) -> str:
    """构建可用脚本列表提示，附加到 SKILL.md 内容后。"""
    if entry.source_path is None:  # type: ignore[union-attr]
        return ""

    skill_dir: Path = entry.source_path.parent.resolve()  # type: ignore[union-attr]
    scripts_dir: Path = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return ""

    script_files: list[str] = [
        f.stem for f in sorted(scripts_dir.glob("*.py"))
        if not f.name.startswith("_")
    ]
    if not script_files:
        return ""

    skill_name: str = entry.name  # type: ignore[union-attr]
    lines: list[str] = ["\n\n## 可用脚本\n"]
    lines.append("通过 `invoke_skill(\"skill_name:script_name\", args='{...}')` 调用：\n")
    for name in script_files:
        lines.append(f"- `{skill_name}:{name}`")

    return "\n".join(lines)

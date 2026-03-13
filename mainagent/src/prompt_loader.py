"""HLSC 主 Agent 的 PromptLoader 实现

复用 SDK 的 TemplatePromptLoader + 业务特有的 context diff 逻辑。
"""

from __future__ import annotations

from pathlib import Path

from agent_sdk.prompt_loader import TemplatePromptLoader


# 提示词根目录（相对于 mainagent/ 目录）
_PROMPTS_DIR = Path("prompts")
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"

# 系统提示词模板（按拼接顺序排列）
SYSTEM_PROMPT_PARTS: list[Path] = [
    _TEMPLATES_DIR / "IDENTITY.md",
    _TEMPLATES_DIR / "SOUL.md",
    _TEMPLATES_DIR / "TOOLS.md",
    _TEMPLATES_DIR / "TASK.md",
    _TEMPLATES_DIR / "SKILL.md",
    _TEMPLATES_DIR / "card.md",
]

AGENTS_MD_PATH = _TEMPLATES_DIR / "AGENTS.md"


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    return TemplatePromptLoader(
        template_parts=SYSTEM_PROMPT_PARTS,
        agent_md_path=AGENTS_MD_PATH,
    )

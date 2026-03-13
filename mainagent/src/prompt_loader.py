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
SYSTEM_PROMPT_PARTS = [
    _TEMPLATES_DIR / "identity.md",
    _TEMPLATES_DIR / "behavior.md",
    _TEMPLATES_DIR / "tool-policy.md",
    _TEMPLATES_DIR / "task-management.md",
    _TEMPLATES_DIR / "skill.md",
    _TEMPLATES_DIR / "card.md",
]

AGENT_MD_PATH = _TEMPLATES_DIR / "agent.md"


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    return TemplatePromptLoader(
        template_parts=SYSTEM_PROMPT_PARTS,
        agent_md_path=AGENT_MD_PATH,
    )

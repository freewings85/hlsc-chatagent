"""Auctioneer Subagent 的 PromptLoader 实现"""

from __future__ import annotations

from pathlib import Path

from agent_sdk.prompt_loader import TemplatePromptLoader

_PROMPTS_DIR: Path = Path("prompts")
_TEMPLATES_DIR: Path = _PROMPTS_DIR / "templates"

SYSTEM_PROMPT_PARTS: list[Path] = [
    _TEMPLATES_DIR / "SYSTEM.md",
]


def create_auctioneer_prompt_loader() -> TemplatePromptLoader:
    """创建 Auctioneer 的 PromptLoader"""
    return TemplatePromptLoader(template_parts=SYSTEM_PROMPT_PARTS)

"""QueryCodingAgent Subagent 的 PromptLoader 实现"""

from __future__ import annotations

from pathlib import Path

from agent_sdk.prompt_loader import TemplatePromptLoader

_PROMPTS_DIR = Path("prompts")
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"

SYSTEM_PROMPT_PARTS = [
    _TEMPLATES_DIR / "system.md",
]


def create_code_agent_prompt_loader() -> TemplatePromptLoader:
    """创建 QueryCodingAgent 的 PromptLoader"""
    return TemplatePromptLoader(template_parts=SYSTEM_PROMPT_PARTS)

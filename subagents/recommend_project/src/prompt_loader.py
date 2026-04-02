"""RecommendProject Subagent 的 PromptLoader 实现"""

from __future__ import annotations

from pathlib import Path

from agent_sdk.prompt_loader import TemplatePromptLoader

# 提示词根目录（相对于 recommend_project/ 目录）
_PROMPTS_DIR = Path("prompts")
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"

# 系统提示词模板（按拼接顺序排列）
SYSTEM_PROMPT_PARTS: list[Path] = [
    _TEMPLATES_DIR / "SYSTEM.md",
]


def create_recommend_project_prompt_loader() -> TemplatePromptLoader:
    """创建 RecommendProject 的 PromptLoader"""
    return TemplatePromptLoader(template_parts=SYSTEM_PROMPT_PARTS)

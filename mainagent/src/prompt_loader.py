"""HLSC 主 Agent 的 PromptLoader 实现

复用 SDK 的 TemplatePromptLoader + 业务特有的 context diff 逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_sdk.prompt_loader import TemplatePromptLoader


# 提示词根目录（相对于 mainagent/ 目录）
_PROMPTS_DIR = Path("prompts")
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"

# 系统提示词模板（按拼接顺序排列）
SYSTEM_PROMPT_PARTS: list[Path] = [
    _TEMPLATES_DIR / "SYSTEM.md",
    _TEMPLATES_DIR / "SOUL.md",
    _TEMPLATES_DIR / "OUTPUT.md",
]

_AGENT_S1_MD_PATH: Path = _TEMPLATES_DIR / "AGENT_S1.md"
_AGENT_S2_MD_PATH: Path = _TEMPLATES_DIR / "AGENT_S2.md"


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader：根据阶段加载对应 AGENT.md。"""

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        # 根据 deps.current_stage 选择 AGENT.md
        path: Path = _AGENT_S2_MD_PATH  # 默认 S2
        if deps is not None and getattr(deps, "current_stage", "") == "S1":
            path = _AGENT_S1_MD_PATH
        if not path.exists():
            return None
        content: str = path.read_text(encoding="utf-8").strip()
        return content or None


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    return MainPromptLoader(template_parts=SYSTEM_PROMPT_PARTS)

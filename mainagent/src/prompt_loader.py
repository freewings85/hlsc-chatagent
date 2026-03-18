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
    _TEMPLATES_DIR / "IDENTITY.md",
    _TEMPLATES_DIR / "SOUL.md",
    _TEMPLATES_DIR / "SAFETY_POLICY.md",
    _TEMPLATES_DIR / "TOOL_POLICY.md",
    _TEMPLATES_DIR / "TASK_POLICY.md",
    _TEMPLATES_DIR / "CONTEXT_POLICY.md",
    _TEMPLATES_DIR / "OUTPUT_POLICY.md",
]

_SCENE_AGENT_FILES: dict[str, Path] = {
    "chat": _TEMPLATES_DIR / "AGENT_CHAT.md",
    "clarify": _TEMPLATES_DIR / "AGENT_CLARIFY.md",
    "execute": _TEMPLATES_DIR / "AGENT_EXECUTE.md",
}


def _resolve_scene_type(request_context: Any) -> str:
    """从 request_context 解析 scene_type，默认返回 clarify。"""
    if request_context is None:
        return "clarify"

    value: Any = None
    if isinstance(request_context, dict):
        scene_info = request_context.get("scene_info")
        if isinstance(scene_info, dict):
            value = scene_info.get("scene_type")
        elif scene_info is not None:
            value = getattr(scene_info, "scene_type", None)
    else:
        scene_info = getattr(request_context, "scene_info", None)
        if scene_info is not None:
            value = getattr(scene_info, "scene_type", None)

    if isinstance(value, str):
        scene = value.strip().lower()
        if scene in _SCENE_AGENT_FILES:
            return scene
    return "clarify"


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader：按 scene_type 动态注入 AGENT 指令。"""

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        request_context = getattr(deps, "request_context", None) if deps is not None else None
        scene_type = _resolve_scene_type(request_context)

        agent_path = _SCENE_AGENT_FILES.get(scene_type, _SCENE_AGENT_FILES["clarify"])
        if not agent_path.exists():
            agent_path = _SCENE_AGENT_FILES["clarify"]
        if not agent_path.exists():
            return None

        content = agent_path.read_text(encoding="utf-8").strip()
        return content or None


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    return MainPromptLoader(template_parts=SYSTEM_PROMPT_PARTS)

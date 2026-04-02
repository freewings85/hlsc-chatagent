"""HLSC 主 Agent 的 PromptLoader 实现

复用 SDK 的 TemplatePromptLoader + 业务特有的 context diff 逻辑。
OUTPUT.md 使用 Jinja2 模板，按 stage/scene 条件渲染。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Template

from agent_sdk.prompt_loader import PromptResult, TemplatePromptLoader


# 提示词根目录（相对于 mainagent/ 目录）
_PROMPTS_DIR = Path("prompts")
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"

# 系统提示词模板（按拼接顺序排列）
# OUTPUT.md 单独处理（Jinja2 渲染），不放入 SYSTEM_PROMPT_PARTS
_STATIC_PARTS: list[Path] = [
    _TEMPLATES_DIR / "SYSTEM.md",
    _TEMPLATES_DIR / "SOUL.md",
]

_OUTPUT_MD_PATH: Path = _TEMPLATES_DIR / "OUTPUT.md"

_AGENT_S1_MD_PATH: Path = _TEMPLATES_DIR / "AGENT_S1.md"
_AGENT_S2_MD_PATH: Path = _TEMPLATES_DIR / "AGENT_S2.md"

# OUTPUT.md Jinja2 模板（懒加载）
_output_template: Template | None = None


def _get_output_template() -> Template | None:
    """加载 OUTPUT.md Jinja2 模板（懒加载）。"""
    global _output_template
    if _output_template is not None:
        return _output_template
    if _OUTPUT_MD_PATH.exists():
        raw: str = _OUTPUT_MD_PATH.read_text(encoding="utf-8").strip()
        if raw:
            _output_template = Template(raw)
            return _output_template
    return None


def _render_output_md(stage: str, scene: str) -> str:
    """用 Jinja2 渲染 OUTPUT.md 模板。"""
    tmpl: Template | None = _get_output_template()
    if tmpl is None:
        return ""
    rendered: str = tmpl.render(stage=stage, scene=scene).strip()
    return rendered


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader：根据阶段和场景加载对应 AGENT.md，渲染 OUTPUT.md。"""

    async def load(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> PromptResult:
        # 获取 stage 和 scene
        stage: str = getattr(deps, "current_stage", "S1") if deps else "S1"
        scene: str = getattr(deps, "current_scene", "none") if deps else "none"

        # 拼接静态部分 + 渲染后的 OUTPUT.md
        system_prompt: str = self._load_system_prompt()
        output_section: str = _render_output_md(stage, scene)
        if output_section:
            system_prompt = system_prompt + "\n\n" + output_section

        # 调父类的 load 获取 context_messages（agent_md + memory_md）
        result: PromptResult = await super().load(
            user_id=user_id,
            session_id=session_id,
            deps=deps,
            message=message,
        )
        # 替换 system_prompt（父类用的是缓存的不含 OUTPUT 的版本）
        result.system_prompt = system_prompt
        return result

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        # 优先使用 hook 设置的场景级 agent_md
        if deps is not None:
            scene_agent_md: str | None = getattr(deps, "current_scene_agent_md", None)
            if scene_agent_md:
                scene_path: Path = _TEMPLATES_DIR / scene_agent_md
                if scene_path.exists():
                    content: str = scene_path.read_text(encoding="utf-8").strip()
                    return content or None

        # 回退：根据 deps.current_stage 选择 AGENT.md
        path: Path = _AGENT_S2_MD_PATH  # 默认 S2
        if deps is not None and getattr(deps, "current_stage", "") == "S1":
            path = _AGENT_S1_MD_PATH
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    return MainPromptLoader(template_parts=_STATIC_PARTS)

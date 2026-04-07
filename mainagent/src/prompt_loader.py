"""HLSC 主 Agent 的 PromptLoader 实现

按场景配置的 prompt_parts 列表拼接 system prompt，
按 agent_md 加载场景级 AGENT.md 注入 context messages。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from agent_sdk.prompt_loader import PromptResult, TemplatePromptLoader
from src.scene_config import registry


# 提示词根目录（基于本文件位置，不依赖 CWD）
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader：按场景 prompt_parts 拼接 system prompt + agent_md 注入。"""

    async def load(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> PromptResult:
        # 获取当前场景
        scene: str = getattr(deps, "current_scene", "guide") if deps else "guide"

        # 按场景的 prompt_parts 拼接 system prompt
        system_prompt: str = self._load_scene_system_prompt(scene)

        # 调父类的 load 获取 context_messages（agent_md + memory_md）
        result: PromptResult = await super().load(
            user_id=user_id,
            session_id=session_id,
            deps=deps,
            message=message,
        )
        # 替换 system_prompt（父类用的是静态 template_parts 版本）
        result.system_prompt = system_prompt
        return result

    def _load_scene_system_prompt(self, scene: str) -> str:
        """按场景配置的 prompt_parts 列表拼接 system prompt。"""
        scene_parts_map: dict[str, list[str]] = registry.get_all_prompt_parts_map()
        prompt_part_files: list[str] = scene_parts_map.get(scene, scene_parts_map.get("guide", []))

        parts: list[str] = []
        for filename in prompt_part_files:
            filepath: Path = _TEMPLATES_DIR / filename
            if filepath.exists():
                content: str = filepath.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)

        return "\n\n".join(parts)

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        # 使用 hook 设置的场景级 agent_md
        if deps is not None:
            scene_agent_md: str | None = getattr(deps, "current_scene_agent_md", None)
            if scene_agent_md:
                scene_path: Path = _TEMPLATES_DIR / scene_agent_md
                if scene_path.exists():
                    content: str = scene_path.read_text(encoding="utf-8").strip()
                    # 内置模板变量
                    content = content.replace("{{current_date}}", date.today().isoformat())
                    # 场景级模板变量（stage_config.yaml 的 vars）
                    scene: str = getattr(deps, "current_scene", "guide")
                    scene_vars: dict[str, str] = registry.get_scene_vars(scene)
                    for key, value in scene_vars.items():
                        content = content.replace("{{" + key + "}}", value)
                    return content or None
        return None


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    # template_parts 传空列表，实际拼接在 _load_scene_system_prompt 中完成
    return MainPromptLoader(template_parts=[])

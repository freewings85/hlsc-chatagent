"""HLSC 主 Agent 的 PromptLoader 实现

按场景配置的 prompt_parts 列表拼接 system prompt，
按 agent_md 加载场景级 AGENT.md 注入 context messages。
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agent_sdk.prompt_loader import PromptResult, TemplatePromptLoader


# 提示词根目录（基于本文件位置，不依赖 CWD）
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"

# 场景配置缓存
_scene_prompt_parts: dict[str, list[str]] | None = None
_scene_vars: dict[str, dict[str, str]] | None = None


def _load_scene_config() -> tuple[dict[str, list[str]], dict[str, dict[str, str]]]:
    """从 stage_config.yaml 加载每个场景的 prompt_parts 和 vars（懒加载 + 缓存）。"""
    global _scene_prompt_parts, _scene_vars
    if _scene_prompt_parts is not None and _scene_vars is not None:
        return _scene_prompt_parts, _scene_vars

    config_path_str: str = os.getenv("STAGE_CONFIG_PATH", "")
    if config_path_str:
        config_path: Path = Path(config_path_str)
    else:
        config_path = Path(__file__).resolve().parent.parent / "stage_config.yaml"

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _scene_prompt_parts = {}
    _scene_vars = {}
    scene_id: str
    scene_data: dict[str, Any]
    for scene_id, scene_data in raw.get("scenes", {}).items():
        _scene_prompt_parts[scene_id] = scene_data.get("prompt_parts", [])
        raw_vars: dict[str, Any] = scene_data.get("vars", {})
        _scene_vars[scene_id] = {k: str(v) for k, v in raw_vars.items()}

    return _scene_prompt_parts, _scene_vars


def _load_scene_prompt_parts() -> dict[str, list[str]]:
    """从 stage_config.yaml 加载每个场景的 prompt_parts。"""
    return _load_scene_config()[0]


def _get_scene_vars(scene: str) -> dict[str, str]:
    """获取指定场景的模板变量。"""
    return _load_scene_config()[1].get(scene, {})


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
        scene_parts_map: dict[str, list[str]] = _load_scene_prompt_parts()
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
                    scene_vars: dict[str, str] = _get_scene_vars(scene)
                    for key, value in scene_vars.items():
                        content = content.replace("{{" + key + "}}", value)
                    return content or None
        return None


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader"""
    # template_parts 传空列表，实际拼接在 _load_scene_system_prompt 中完成
    return MainPromptLoader(template_parts=[])

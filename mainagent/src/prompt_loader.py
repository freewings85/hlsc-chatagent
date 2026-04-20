"""HLSC 主 Agent 的 PromptLoader 实现

按 stage_config.yaml 里的声明加载场景 prompt。
调用方在 request_context.scene 指定场景（orchestrator 和直连两种模式都一样），
PreRunHook 解包到 deps.current_scene，本模块据此查 stage_config 加载 prompt_parts + agent_md。

场景未指定或未在 stage_config.yaml 中声明 → 报错（不在服务范围）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from agent_sdk.prompt_loader import PromptResult, TemplatePromptLoader
from src.scene_config import SceneConfig, registry


# 提示词根目录（基于本文件位置，不依赖 CWD）
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"


class MissingSceneError(Exception):
    """deps.current_scene 为空——请求未指定场景，不在服务范围。"""


def _read_file(relative_path: str) -> str:
    """读 templates 目录下的文件，不存在返回空串。"""
    path: Path = _TEMPLATES_DIR / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _resolve_scene(deps: Any | None) -> SceneConfig:
    """从 deps.current_scene 取出场景配置。空或找不到都抛错。"""
    scene_id: str = getattr(deps, "current_scene", "") if deps else ""
    if not scene_id:
        raise MissingSceneError("请求未指定场景（deps.current_scene 为空），不在服务范围")
    # registry.get_scene 找不到会抛 SceneNotFoundError
    return registry.get_scene(scene_id)


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader。按 stage_config.yaml 加载场景 prompt。"""

    async def load(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> PromptResult:
        scene: SceneConfig = _resolve_scene(deps)

        # 通用 system prompt：按场景 prompt_parts 拼接
        system_parts: list[str] = []
        for filename in scene.prompt_parts:
            content: str = _read_file(filename)
            if content:
                system_parts.append(content)
        system_prompt: str = "\n\n".join(system_parts)

        # 调父类拿 context_messages（会调 get_agent_md_content）
        result: PromptResult = await super().load(
            user_id=user_id,
            session_id=session_id,
            deps=deps,
            message=message,
        )
        result.system_prompt = system_prompt
        return result

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        """按 stage_config.yaml 里 agent_md 声明的文件顺序拼接。"""
        scene: SceneConfig = _resolve_scene(deps)

        parts: list[str] = []
        for filename in scene.agent_md:
            content: str = _read_file(filename)
            if content:
                parts.append(content)

        if not parts:
            return None

        merged: str = "\n\n".join(parts)
        # 替换模板变量（仅 current_date，场景变量由 orchestrator 直接在 context 里传）
        merged = merged.replace("{{current_date}}", date.today().isoformat())
        return merged


def create_main_prompt_loader() -> TemplatePromptLoader:
    """创建主 Agent 的 PromptLoader。"""
    return MainPromptLoader(template_parts=[])

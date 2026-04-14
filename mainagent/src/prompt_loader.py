"""HLSC 主 Agent 的 PromptLoader 实现

按场景约定组装 system prompt 和 agent_md。
orchestrator 通过 request_context.orchestrator.scenario 指定场景，
PreRunHook 解包到 deps.current_scene 后本模块按约定加载对应文件。

静态前缀组成：
    system_prompt = SYSTEM.md + SOUL.md（通用行为准则）
    agent_md      = {scene}/AGENT.md + orchestrated/AGENT.md + {scene}/OUTPUT.md
                   （场景角色 + 编排机制 + 输出规范）
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from agent_sdk.prompt_loader import PromptResult, TemplatePromptLoader


# 提示词根目录（基于本文件位置，不依赖 CWD）
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"


def _read_file(relative_path: str) -> str:
    """读 templates 目录下的文件，不存在返回空串。"""
    path: Path = _TEMPLATES_DIR / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


class MainPromptLoader(TemplatePromptLoader):
    """MainAgent PromptLoader。按场景加载提示词。"""

    async def load(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> PromptResult:
        # 通用 system prompt：SYSTEM.md + SOUL.md
        system_parts: list[str] = []
        for filename in ["SYSTEM.md", "SOUL.md"]:
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
        """按约定拼装：{scene}/AGENT.md + orchestrated/AGENT.md + {scene}/OUTPUT.md。"""
        scene: str = getattr(deps, "current_scene", "") if deps else ""
        if not scene:
            return None

        parts: list[str] = []
        for filename in [f"{scene}/AGENT.md", "orchestrated/AGENT.md", f"{scene}/OUTPUT.md"]:
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

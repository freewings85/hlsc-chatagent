"""按 AgentSpec 驱动的 PromptLoader。

继承 SDK 的 TemplatePromptLoader，使：
- `spec.prompt`（agent_registry 在加载时已把 prompt_parts 拼好）直接作为 system_prompt
- `spec.agent_md_files` 走基类 `get_agent_md_content()` 钩子，被注入为 context message

基类 load() 流程会自动追加 agent_md + MEMORY.md，这里只需覆盖两个点。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_sdk.prompt_loader import TemplatePromptLoader

from src.agent_registry import AgentSpec


class SpecPromptLoader(TemplatePromptLoader):
    """/chat/stream2 的 per-agent-type PromptLoader。每个预构建的 Agent 配一个。"""

    def __init__(self, spec: AgentSpec, templates_root: Path) -> None:
        # 基类 __init__ 的 template_parts 我们不用（spec.prompt 已经是拼好的完整内容）
        super().__init__(template_parts=[])
        self._system_prompt: str = spec.prompt
        self._agent_md_files: tuple[str, ...] = spec.agent_md_files
        self._templates_root: Path = templates_root

    def _load_system_prompt(self) -> str:
        """覆盖基类——直接返回 AgentSpec 编译好的 prompt，不读文件。"""
        return self._system_prompt

    async def get_agent_md_content(
        self,
        user_id: str,
        session_id: str,
        deps: Any | None = None,
        message: str | None = None,
    ) -> str | None:
        """按 spec.agent_md_files 顺序读 templates/ 下文件拼接。"""
        if not self._agent_md_files:
            return None
        parts: list[str] = []
        for rel in self._agent_md_files:
            path: Path = self._templates_root / rel
            if not path.is_file():
                continue
            content: str = path.read_text(encoding="utf-8").rstrip()
            if content:
                parts.append(content)
        if not parts:
            return None
        return "\n\n".join(parts)

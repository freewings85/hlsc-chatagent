"""PromptLoader：系统提示词加载的 service 接口

用户通过实现 PromptLoader 协议来控制 system prompt 和 context messages 的加载逻辑。
框架提供两个内置实现：
- StaticPromptLoader — 固定字符串（subagent 用）
- TemplatePromptLoader — 模板目录拼接 + context 文件（主 agent 用）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic_ai.messages import ModelRequest, UserPromptPart


@dataclass
class PromptResult:
    """PromptLoader 的返回值"""

    system_prompt: str
    context_messages: list[ModelRequest] = field(default_factory=list)


@runtime_checkable
class PromptLoader(Protocol):
    """系统提示词加载协议。

    每次对话开始时调用 load()，返回 system_prompt 和 context_messages。
    """

    async def load(self, user_id: str, session_id: str, **kwargs: object) -> PromptResult: ...


class StaticPromptLoader:
    """固定字符串 prompt loader（subagent / 测试用）"""

    def __init__(self, system_prompt: str) -> None:
        self._prompt = system_prompt

    async def load(self, user_id: str, session_id: str, **kwargs: object) -> PromptResult:
        return PromptResult(system_prompt=self._prompt, context_messages=[])


# ── TemplatePromptLoader 约定路径 ──
_MEMORY_MD_PATH = "/{user_id}/MEMORY.md"


class TemplatePromptLoader:
    """模板目录拼接 + context 文件的 prompt loader

    约定：
    - MEMORY.md 固定在 {USER_FS_DIR}/{user_id}/MEMORY.md（有则注入，无则跳过）

    Args:
        template_parts: 模板文件路径列表，按顺序拼接为 system_prompt
        agent_md_path: AGENTS.md 路径（项目级业务配置），有则注入为 context_message，None 则跳过
    """

    def __init__(
        self,
        template_parts: list[str | Path],
        agent_md_path: str | Path | None = None,
    ) -> None:
        self._template_parts = [Path(p) for p in template_parts]
        self._agent_md_path = Path(agent_md_path) if agent_md_path else None
        self._system_prompt_cache: str | None = None

    def _load_system_prompt(self) -> str:
        """加载并拼接系统提示词模板文件"""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache
        parts: list[str] = []
        for path in self._template_parts:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
        self._system_prompt_cache = "\n\n".join(parts)
        return self._system_prompt_cache

    async def load(self, user_id: str, session_id: str, **kwargs: object) -> PromptResult:
        system_prompt = self._load_system_prompt()
        context_messages: list[ModelRequest] = []

        # AGENTS.md / agent.md（项目级业务配置）
        if self._agent_md_path and self._agent_md_path.exists():
            content = self._agent_md_path.read_text(encoding="utf-8").strip()
            filename = self._agent_md_path.name
            if content:
                context_messages.append(ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of {filename} (project instructions):\n\n{content}",
                    )],
                    metadata={"is_meta": True, "source": "agent_md"},
                ))

        # MEMORY.md
        memory_md = await self._read_memory_md(user_id)
        if memory_md:
            context_messages.append(ModelRequest(
                parts=[UserPromptPart(
                    content=f"Contents of MEMORY.md (auto-memory, persists across sessions):\n\n{memory_md}",
                )],
                metadata={"is_meta": True, "source": "memory"},
            ))

        return PromptResult(system_prompt=system_prompt, context_messages=context_messages)

    async def _read_memory_md(self, user_id: str) -> str | None:
        """从 user_fs_backend 读取 MEMORY.md"""
        from agent_sdk.config import get_user_fs_backend

        backend = get_user_fs_backend()
        path = _MEMORY_MD_PATH.format(user_id=user_id)
        if not await backend.aexists(path):
            return None
        results = await backend.adownload_files([path])
        if results and results[0].content is not None:
            try:
                return results[0].content.decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None

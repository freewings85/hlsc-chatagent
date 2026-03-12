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


class TemplatePromptLoader:
    """模板目录拼接 + context 文件的 prompt loader（主 agent 用）

    Args:
        template_parts: 模板文件路径列表，按顺序拼接为 system_prompt
        agent_md_path: agent.md 路径（项目级业务配置），注入为 context_message
        memory_md_path: memory.md 路径模板（含 {user_id}），从 user_fs_backend 读取
        user_fs_backend: 用户级文件系统后端（读取 memory.md）
    """

    def __init__(
        self,
        template_parts: list[str | Path],
        agent_md_path: str | Path | None = None,
        memory_md_path: str | None = None,
        user_fs_backend: object | None = None,
    ) -> None:
        self._template_parts = [Path(p) for p in template_parts]
        self._agent_md_path = Path(agent_md_path) if agent_md_path else None
        self._memory_md_path = memory_md_path
        self._user_fs_backend = user_fs_backend
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

        # agent.md
        if self._agent_md_path and self._agent_md_path.exists():
            content = self._agent_md_path.read_text(encoding="utf-8").strip()
            if content:
                context_messages.append(ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of agent.md (project instructions):\n\n{content}",
                    )],
                    metadata={"is_meta": True, "source": "agent_md"},
                ))

        # memory.md（需要 user_fs_backend）
        if self._memory_md_path and self._user_fs_backend is not None:
            memory_md = await self._read_memory_md(user_id)
            if memory_md:
                context_messages.append(ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of memory.md (auto-memory, persists across sessions):\n\n{memory_md}",
                    )],
                    metadata={"is_meta": True, "source": "memory"},
                ))

        return PromptResult(system_prompt=system_prompt, context_messages=context_messages)

    async def _read_memory_md(self, user_id: str) -> str | None:
        """从 user_fs_backend 读取 memory.md"""
        if self._memory_md_path is None or self._user_fs_backend is None:
            return None
        path = self._memory_md_path.format(user_id=user_id)
        backend = self._user_fs_backend
        if not await backend.aexists(path):  # type: ignore[union-attr]
            return None
        results = await backend.adownload_files([path])  # type: ignore[union-attr]
        if results and results[0].content is not None:
            try:
                return results[0].content.decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None

"""PromptBuilder：加载系统提示词 + 构建上下文消息（agent.md / memory.md）"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from src.common.filesystem_backend import BackendProtocol

# 代码内模板路径
_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
_SYSTEM_MAIN_PROMPT: Path = _TEMPLATES_DIR / "system-main-prompt.md"

# FileSystemBackend 中的用户空间路径（virtual_mode，相对于 data_dir）
_AGENT_MD_PATH = "/{user_id}/agent.md"
_MEMORY_MD_PATH = "/{user_id}/memory.md"


class PromptBuilder:
    """加载系统提示词和上下文消息。

    - system_prompt: 从代码内模板加载，传给 agent 的 system_prompt 参数
    - context_messages: agent.md / memory.md 等，作为 is_meta 消息注入到 message_history 前面
    """

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend: BackendProtocol = backend
        self._system_prompt_cache: str | None = None

    def build_system_prompt(self) -> str:
        """加载系统提示词（代码内模板，可缓存）。"""
        if self._system_prompt_cache is None:
            self._system_prompt_cache = _SYSTEM_MAIN_PROMPT.read_text(encoding="utf-8").strip()
        return self._system_prompt_cache

    async def build_context_messages(self, user_id: str) -> list[ModelRequest]:
        """构建上下文消息（agent.md + memory.md），带 is_meta 标记。

        这些消息在每次 API 调用前临时 prepend 到 messages[0]，不存入历史。
        """
        messages: list[ModelRequest] = []

        # agent.md（对应 Claude Code 的 CLAUDE.md）
        agent_md_path: str = _AGENT_MD_PATH.format(user_id=user_id)
        agent_md: str | None = await self._read_if_exists(agent_md_path)
        if agent_md:
            messages.append(
                ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of agent.md (project instructions):\n\n{agent_md}",
                    )],
                    metadata={"is_meta": True, "source": "agent_md"},
                )
            )

        # memory.md（对应 Claude Code 的 MEMORY.md）
        memory_md_path: str = _MEMORY_MD_PATH.format(user_id=user_id)
        memory_md: str | None = await self._read_if_exists(memory_md_path)
        if memory_md:
            messages.append(
                ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of memory.md (auto-memory, persists across sessions):\n\n{memory_md}",
                    )],
                    metadata={"is_meta": True, "source": "memory"},
                )
            )

        return messages

    async def _read_if_exists(self, path: str) -> str | None:
        """读取文件，不存在返回 None。"""
        if not await self._backend.aexists(path):
            return None
        content: str = await self._backend.aread(path)
        if content.startswith("Error:"):  # pragma: no cover — backend 错误防御
            return None
        # aread 返回带行号的格式，这里需要原始内容
        return await self._read_raw(path)

    async def _read_raw(self, path: str) -> str | None:
        """读取文件原始内容（不带行号格式）。"""
        # BackendProtocol.read() 返回带行号的格式化内容
        # 对于注入到消息的内容，我们需要原始文本
        # 使用 download_files 获取原始 bytes
        results = await self._backend.adownload_files([path])
        if results and results[0].content is not None:
            try:
                return results[0].content.decode("utf-8")
            except UnicodeDecodeError:  # pragma: no cover
                return None
        return None  # pragma: no cover — download_files 返回空结果

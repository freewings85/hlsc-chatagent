"""PromptBuilder：加载系统提示词 + 构建上下文消息（agent.md / memory.md）

所有提示词文件统一存放在 ./prompts/ 目录下，通过管理 API 可查看和编辑：
- prompts/templates/*.md — 系统提示词模板（按顺序拼接）
- prompts/agent.md — 项目级业务配置
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from agent_sdk._common.filesystem_backend import BackendProtocol

# 提示词根目录（必须通过 PROMPTS_DIR 环境变量配置）
_PROMPTS_DIR_RAW: str | None = os.getenv("PROMPTS_DIR")
if not _PROMPTS_DIR_RAW:
    raise RuntimeError(
        "环境变量 PROMPTS_DIR 未配置。"
        "每个 Agent 必须在 .env.local 中设置 PROMPTS_DIR 指向自己的 prompts 目录。"
    )
_PROMPTS_DIR: Path = Path(_PROMPTS_DIR_RAW)
_TEMPLATES_DIR: Path = _PROMPTS_DIR / "templates"

# 系统提示词模板（按拼接顺序排列，见 templates/README.md）
_SYSTEM_PROMPT_PARTS: list[Path] = [
    _TEMPLATES_DIR / "identity.md",
    _TEMPLATES_DIR / "behavior.md",
    _TEMPLATES_DIR / "tool-policy.md",
    _TEMPLATES_DIR / "task-management.md",
    _TEMPLATES_DIR / "skill.md",
    _TEMPLATES_DIR / "card.md",
]

# agent.md 路径（项目级业务配置）
_AGENT_MD_PATH: Path = _TEMPLATES_DIR / "agent.md"

# user_fs backend 中的路径（按用户隔离）
_MEMORY_MD_PATH = "/{user_id}/memory.md"


class PromptBuilder:
    """加载系统提示词和上下文消息。

    - system_prompt: 从 prompts/templates/ 加载，传给 agent 的 system_prompt 参数
    - context_messages: agent.md / memory.md 等，作为 is_meta 消息注入到 message_history 前面

    使用 user_fs_backend 读取 memory.md（按用户隔离），
    agent.md 和 templates 直接从本地 prompts/ 目录读取。
    """

    def __init__(
        self,
        user_fs_backend: BackendProtocol,
        agent_fs_backend: BackendProtocol | None = None,
    ) -> None:
        self._user_fs_backend: BackendProtocol = user_fs_backend
        self._system_prompt_cache: str | None = None

    @staticmethod
    def load_system_prompt() -> str:
        """加载系统提示词（多文件拼接，顺序见 templates/README.md）。"""
        parts: list[str] = []
        for path in _SYSTEM_PROMPT_PARTS:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
        return "\n\n".join(parts)

    @staticmethod
    def load_agent_md() -> str | None:
        """加载 agent.md（项目级业务配置）。"""
        if _AGENT_MD_PATH.exists():
            content = _AGENT_MD_PATH.read_text(encoding="utf-8").strip()
            return content if content else None
        return None

    def build_system_prompt(self) -> str:
        """加载系统提示词（带实例缓存）。"""
        if self._system_prompt_cache is None:
            self._system_prompt_cache = self.load_system_prompt()
        return self._system_prompt_cache

    async def build_context_messages(self, user_id: str) -> list[ModelRequest]:
        """构建上下文消息（agent.md + memory.md），带 is_meta 标记。

        这些消息在每次 API 调用前临时 prepend 到 messages[0]，不存入历史。
        """
        messages: list[ModelRequest] = []

        # agent.md（项目级，从 prompts/ 目录直接读取）
        agent_md = self.load_agent_md()
        if agent_md:
            messages.append(
                ModelRequest(
                    parts=[UserPromptPart(
                        content=f"Contents of agent.md (project instructions):\n\n{agent_md}",
                    )],
                    metadata={"is_meta": True, "source": "agent_md"},
                )
            )

        # memory.md（用户级，从 user_fs_backend 读取）
        memory_md_path: str = _MEMORY_MD_PATH.format(user_id=user_id)
        memory_md: str | None = await self._read_if_exists(
            self._user_fs_backend, memory_md_path,
        )
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

    async def _read_if_exists(self, backend: BackendProtocol, path: str) -> str | None:
        """读取文件，不存在返回 None。"""
        if not await backend.aexists(path):
            return None
        content: str = await backend.aread(path)
        if content.startswith("Error:"):  # pragma: no cover — backend 错误防御
            return None
        # aread 返回带行号的格式，这里需要原始内容
        return await self._read_raw(backend, path)

    async def _read_raw(self, backend: BackendProtocol, path: str) -> str | None:
        """读取文件原始内容（不带行号格式）。"""
        results = await backend.adownload_files([path])
        if results and results[0].content is not None:
            try:
                return results[0].content.decode("utf-8")
            except UnicodeDecodeError:  # pragma: no cover
                return None
        return None  # pragma: no cover — download_files 返回空结果

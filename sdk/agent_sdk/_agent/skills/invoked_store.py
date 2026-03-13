"""InvokedSkillStore：已激活 skill 的 session 级持久化存储。

设计依据（Decision 3）：
- Skill 工具执行后，SKILL.md 内容进入消息历史（tool_result）
- compact 触发后历史被截断，tool_result 消失，LLM 丢失 skill 指令（隐式失效）
- 解决方案：把 invoked skill 内容从消息历史中分离，存到 session 文件
- 每次 ModelRequestNode 前重新注入为 system-reminder attachment

与 Claude Code invokedSkills Map 的区别：
- Claude Code：进程级 Map，进程重启后丢失
- 我们：session 文件（invoked_skills.json），进程重启后可从文件恢复

路径约定：
  /{user_id}/sessions/{session_id}/invoked_skills.json

注意：使用 aexists/adownload_files/awrite/adelete 而非 aread，
因为 aread 是 LLM 工具专用（带行号格式化、不返回 None）。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_sdk._common.filesystem_backend import BackendProtocol


@dataclass
class InvokedSkill:
    """一条已激活的 skill 记录。"""

    name: str
    content: str
    invoked_at: datetime


def _invoked_skills_path(user_id: str, session_id: str) -> str:
    return f"/{user_id}/sessions/{session_id}/invoked_skills.json"


class InvokedSkillStore:
    """已激活 skill 的 session 级持久化存储。

    职责：
    - load()    — 从 session 文件恢复内存字典
    - record()  — upsert 一条记录（内存 + 文件）
    - get_all() — 返回当前内存字典（供 PreModelCallMessageService 读取）
    """

    def __init__(
        self,
        backend: BackendProtocol,
        user_id: str,
        session_id: str,
    ) -> None:
        self._backend = backend
        self._user_id = user_id
        self._session_id = session_id
        self._store: dict[str, InvokedSkill] = {}
        self._lock = asyncio.Lock()

    def _path(self) -> str:
        return _invoked_skills_path(self._user_id, self._session_id)

    async def load(self) -> None:
        """从 session 文件恢复内存字典（进程重启后调用）。

        文件不存在时静默跳过（空字典）。
        """
        async with self._lock:
            path = self._path()
            if not await self._backend.aexists(path):
                return
            responses = await self._backend.adownload_files([path])
            resp = responses[0]
            if resp.error is not None or resp.content is None:
                return
            raw = resp.content.decode("utf-8").strip()
            if not raw:
                return
            try:
                data: dict[str, dict[str, str]] = json.loads(raw)
                for name, rec in data.items():
                    self._store[name] = InvokedSkill(
                        name=rec["name"],
                        content=rec["content"],
                        invoked_at=datetime.fromisoformat(rec["invoked_at"]),
                    )
            except (json.JSONDecodeError, KeyError):
                # 文件损坏，从空白开始
                self._store.clear()

    async def record(self, skill: InvokedSkill) -> None:
        """记录一条已激活的 skill（upsert，内存 + 文件）。"""
        async with self._lock:
            self._store[skill.name] = skill
            await self._flush_locked()

    def get_all(self) -> dict[str, InvokedSkill]:
        """返回当前所有已激活的 skill（只读快照）。"""
        return dict(self._store)

    async def _flush_locked(self) -> None:
        """将内存字典写入 session 文件（需持有 _lock）。

        使用 delete-then-write 模式（同 MemoryMessageService._overwrite_file）。
        """
        data = {
            name: {
                "name": skill.name,
                "content": skill.content,
                "invoked_at": skill.invoked_at.isoformat(),
            }
            for name, skill in self._store.items()
        }
        content = json.dumps(data, ensure_ascii=False, indent=2)
        path = self._path()

        if await self._backend.aexists(path):
            deleted = await self._backend.adelete(path)
            if not deleted:
                raise OSError(f"无法删除旧 invoked_skills 文件: {path}")

        result = await self._backend.awrite(path, content)
        if result.error is not None:
            raise OSError(f"写入 invoked_skills 失败: {path}: {result.error}")

"""MemoryMessageService：会话消息工作集管理接口。

定义消息工作集的三个核心操作：
- load()         — 加载工作集
- update()       — compact 后全量替换
- insert_batch() — 追加新消息
"""

from __future__ import annotations

import abc

from agent_sdk._agent.agent_message import AgentMessage


class MemoryMessageService(abc.ABC):
    """会话消息工作集管理接口。"""

    @abc.abstractmethod
    async def load(self, user_id: str, session_id: str) -> list[AgentMessage]:
        """加载消息工作集。"""

    @abc.abstractmethod
    async def update(
        self,
        user_id: str,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        """全量替换工作集（compact 后调用）。"""

    @abc.abstractmethod
    async def insert_batch(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[AgentMessage],
    ) -> None:
        """追加新消息到工作集。"""

"""SqliteMemoryMessageService：SQLite 持久化实现。

每用户一个 SQLite 数据库文件：{base_dir}/{user_id}/messages.db
WAL 模式，读写不阻塞。
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from src.agent.agent_message import (
    AgentMessage,
    deserialize_agent_messages,
    serialize_single_agent_message,
    should_persist,
)
from src.agent.message.message_repair import (
    find_missing_tool_call_ids,
    load_transcript,
    repair_messages,
)
from src.agent.message.message_service import MemoryMessageService

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_json TEXT NOT NULL
);
"""

_CREATE_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


class SqliteMemoryMessageService(MemoryMessageService):
    """SQLite 持久化的消息工作集。

    每用户一个 db 文件，连接按 user_id 缓存复用。
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir
        self._connections: dict[str, aiosqlite.Connection] = {}

    def _db_path(self, user_id: str) -> str:
        return os.path.join(self._base_dir, user_id, "messages.db")

    async def _get_conn(self, user_id: str) -> aiosqlite.Connection:
        if user_id in self._connections:
            return self._connections[user_id]

        db_path = self._db_path(user_id)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.execute(_CREATE_INDEX_SQL)
        await conn.commit()

        self._connections[user_id] = conn
        return conn

    async def load(self, user_id: str, session_id: str) -> list[AgentMessage]:
        """从 SQLite 加载消息，加载后自动修复 tool_call 配对问题。"""
        conn = await self._get_conn(user_id)
        cursor = await conn.execute(
            "SELECT message_json FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return []

        messages: list[AgentMessage] = []
        for (json_str,) in rows:
            messages.extend(deserialize_agent_messages(json_str))

        # 加载时修复
        if messages and find_missing_tool_call_ids(messages):
            from src.config.settings import get_user_fs_backend

            backend = get_user_fs_backend()
            transcript = await load_transcript(backend, user_id, session_id)
            repaired = repair_messages(messages, transcript)
            if repaired is not messages:
                messages = repaired
                await self._overwrite(conn, session_id, messages)

        return messages

    async def update(
        self,
        user_id: str,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        """全量替换（compact 后调用）。"""
        persist = [m for m in messages if should_persist(m)]
        conn = await self._get_conn(user_id)
        await self._overwrite(conn, session_id, persist)

    async def insert_batch(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[AgentMessage],
    ) -> None:
        """追加新消息。"""
        persist = [m for m in new_messages if should_persist(m)]
        if not persist:
            return

        conn = await self._get_conn(user_id)
        await conn.executemany(
            "INSERT INTO messages (session_id, message_json) VALUES (?, ?)",
            [(session_id, serialize_single_agent_message(m)) for m in persist],
        )
        await conn.commit()

    async def _overwrite(
        self,
        conn: aiosqlite.Connection,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        """事务内全量替换某 session 的消息。"""
        await conn.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session_id,),
        )
        if messages:
            await conn.executemany(
                "INSERT INTO messages (session_id, message_json) VALUES (?, ?)",
                [(session_id, serialize_single_agent_message(m)) for m in messages],
            )
        await conn.commit()

    async def close(self) -> None:
        """关闭所有连接。"""
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()

"""PostgreSQL 存储后端实现"""

from __future__ import annotations

from src.common.filesystem_backend import (
    EditResult,
    FileInfo,
    FileSystemBackend,
    GrepMatch,
    WriteResult,
)


class PgFileSystemBackend:
    """基于 PostgreSQL 的 FileSystemBackend 实现。

    表结构：files(path, content, created_at, modified_at)
    后续实现参考 langchain deepagents PostgresBackend。
    """

    async def read(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        raise NotImplementedError

    async def write(self, path: str, content: str) -> WriteResult:
        raise NotImplementedError

    async def edit(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        raise NotImplementedError

    async def ls_info(self, path: str) -> list[FileInfo]:
        raise NotImplementedError

    async def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        raise NotImplementedError

    async def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise NotImplementedError

    async def delete(self, path: str) -> bool:
        raise NotImplementedError

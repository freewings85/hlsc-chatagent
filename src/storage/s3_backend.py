"""S3/MinIO 对象存储后端实现"""

from __future__ import annotations

from src.common.filesystem_backend import (
    EditResult,
    FileInfo,
    FileSystemBackend,
    GrepMatch,
    WriteResult,
)


class S3FileSystemBackend:
    """基于 S3/MinIO 的 FileSystemBackend 实现。

    后续实现参考 langchain deepagents S3Backend。
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

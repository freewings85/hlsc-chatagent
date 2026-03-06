"""Protocol definition for pluggable memory backends.

Ported from deepagents.backends.protocol (langchain deepagents).
"""

import abc
import asyncio
from dataclasses import dataclass
from typing import Any, Literal, NotRequired

from typing_extensions import TypedDict

FileOperationError = Literal[
    "file_not_found",
    "permission_denied",
    "is_directory",
    "invalid_path",
]


@dataclass
class FileDownloadResponse:
    """Result of a single file download operation."""

    path: str
    content: bytes | None = None
    error: FileOperationError | None = None


@dataclass
class FileUploadResponse:
    """Result of a single file upload operation."""

    path: str
    error: FileOperationError | None = None


class FileInfo(TypedDict):
    """Structured file listing info."""

    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]
    modified_at: NotRequired[str]


class GrepMatch(TypedDict):
    """Structured grep match entry."""

    path: str
    line: int
    text: str


@dataclass
class WriteResult:
    """Result from backend write operations."""

    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    """Result from backend edit operations."""

    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None


class BackendProtocol(abc.ABC):
    """Protocol for pluggable memory backends.

    Ported from deepagents.backends.protocol.BackendProtocol.
    Sync methods + async wrappers via asyncio.to_thread.
    """

    def ls_info(self, path: str) -> list[FileInfo]:
        raise NotImplementedError

    async def als_info(self, path: str) -> list[FileInfo]:
        return await asyncio.to_thread(self.ls_info, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        raise NotImplementedError

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        raise NotImplementedError

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        raise NotImplementedError

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        raise NotImplementedError

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        raise NotImplementedError

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise NotImplementedError

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        raise NotImplementedError

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    async def aexists(self, path: str) -> bool:
        return await asyncio.to_thread(self.exists, path)

    def delete(self, path: str) -> bool:
        raise NotImplementedError

    async def adelete(self, path: str) -> bool:
        return await asyncio.to_thread(self.delete, path)

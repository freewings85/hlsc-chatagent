"""存储后端协议（纯接口）— 参考 langchain deepagents BackendProtocol"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FileInfo:
    """文件/目录信息。"""

    path: str
    is_dir: bool = False
    size: int = 0
    modified_at: str = ""


@dataclass
class WriteResult:
    """写入结果。"""

    path: str
    success: bool
    message: str = ""


@dataclass
class EditResult:
    """编辑结果。"""

    path: str
    success: bool
    message: str = ""


@dataclass
class GrepMatch:
    """搜索匹配结果。"""

    path: str
    line_number: int
    content: str


class FileSystemBackend(Protocol):
    """虚拟文件系统接口。

    所有路径为绝对路径（如 /sessions/xxx/messages.json）。
    错误返回可读字符串而非抛异常。
    """

    async def read(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        """读取文件内容，支持分页（offset=行偏移，limit=行数）。"""
        ...

    async def write(self, path: str, content: str) -> WriteResult:
        """写入文件（创建或覆盖）。"""
        ...

    async def edit(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """编辑文件：替换 old_string 为 new_string。"""
        ...

    async def ls_info(self, path: str) -> list[FileInfo]:
        """列出目录内容，返回文件/目录信息列表。"""
        ...

    async def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """按 glob 模式搜索文件。"""
        ...

    async def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """按正则搜索文件内容。无效正则返回错误字符串。"""
        ...

    async def exists(self, path: str) -> bool:
        """检查路径是否存在。"""
        ...

    async def delete(self, path: str) -> bool:
        """删除文件或目录。"""
        ...

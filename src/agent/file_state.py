"""FileStateTracker：追踪工具对文件的读写状态，用于生成 changed_files attachment。

设计参考 Claude Code 的 readFileState / gqY (changed_files attachment) 逻辑：
- Read 工具调用 on_read()，记录 {content, mtime, offset, limit}
- Edit/Write 工具调用 on_write()，更新 {content, mtime, offset=None, limit=None}
- get_changed_files() 只返回满足两个条件的文件：
    1. offset/limit 均为 None（说明完整读过，而非局部读）
    2. 当前磁盘 mtime != 记录时的 mtime（说明文件已被外部修改）
- compact 后调用 clear() 重置状态
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileEntry:
    """单个文件的访问记录。"""

    content: str
    timestamp: float  # mtime（os.stat().st_mtime）at read/write time
    offset: int | None  # None 表示未指定偏移（完整读）
    limit: int | None  # None 表示未指定行数限制（完整读）


@dataclass
class ChangedFile:
    """被外部修改过的文件信息（用于 attachment 注入）。"""

    path: str
    old_content: str  # 上次读取时的内容
    current_mtime: float  # 当前磁盘 mtime


class FileStateTracker:
    """追踪 Agent 本轮会话中读写过的文件状态。

    与 Claude Code readFileState (Map<string, FileState>) 对应。
    """

    def __init__(self) -> None:
        self._entries: dict[str, FileEntry] = {}

    def on_read(
        self,
        path: str,
        content: str,
        mtime: float,
        offset: int | None,
        limit: int | None,
    ) -> None:
        """Read 工具调用后记录文件状态。

        offset/limit 不为 None 时，说明只读了部分内容，
        get_changed_files() 会跳过这种 entry（与 Claude Code 逻辑一致）。
        """
        self._entries[path] = FileEntry(
            content=content,
            timestamp=mtime,
            offset=offset,
            limit=limit,
        )

    def on_write(self, path: str, content: str, mtime: float) -> None:
        """Edit/Write 工具调用后更新文件状态。

        offset/limit 设为 None，表示已知完整内容，
        但 mtime 更新为写入后的时间戳，避免下次 get_changed_files() 误报。
        """
        self._entries[path] = FileEntry(
            content=content,
            timestamp=mtime,
            offset=None,
            limit=None,
        )

    def get_changed_files(self) -> list[ChangedFile]:
        """返回被外部修改（mtime 变化）的完整读文件列表。

        过滤规则（对应 Claude Code gqY 的 changed_files 生成逻辑）：
        - 跳过 offset/limit 不为 None 的 entry（局部读，无法判断是否变化）
        - 检查当前磁盘 mtime，若与记录不同则视为 changed
        """
        changed: list[ChangedFile] = []
        for path, entry in self._entries.items():
            # 局部读的文件跳过
            if entry.offset is not None or entry.limit is not None:
                continue
            try:
                current_mtime = Path(path).stat().st_mtime
            except OSError:
                continue
            if current_mtime != entry.timestamp:
                changed.append(
                    ChangedFile(
                        path=path,
                        old_content=entry.content,
                        current_mtime=current_mtime,
                    )
                )
        return changed

    def clear(self) -> None:
        """compact 后调用，清空所有记录。"""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

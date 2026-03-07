"""文件系统工具：Read, Edit, Write, Glob, Grep。

工具签名遵循 Pydantic AI 规范：
    async def tool(ctx: RunContext[AgentDeps], ...) -> str

设计参考 Claude Code 的 Read (l9/z_4)、Edit、Write、Glob、Grep 实现：
- Read：调用 backend.aread()，并通过 FileStateTracker 记录文件状态
- Edit：调用 backend.aedit()，写入后更新 FileStateTracker
- Write：调用 backend.awrite()，写入后更新 FileStateTracker
- Glob：调用 backend.aglob_info()，返回匹配路径列表
- Grep：调用 backend.agrep_raw()，返回 path:line: text 格式

backend 优先使用 ctx.deps.backend，为 None 时 fallback 到 get_backend()（全局单例）。
"""

from pathlib import Path

from pydantic_ai import RunContext

from src.agent.deps import AgentDeps  # noqa: F401 (needed for RunContext type)
from src.common.filesystem_backend import BackendProtocol
from src.config.settings import get_backend as _get_backend

# Read 工具：默认不限制 offset/limit（整个文件读取）时的"无限制"标志
_DEFAULT_LIMIT = 2000


def _backend(ctx: RunContext[AgentDeps]) -> BackendProtocol:
    return ctx.deps.backend or _get_backend()


async def read(
    ctx: RunContext[AgentDeps],
    file_path: str,
    offset: int = 0,
    limit: int = _DEFAULT_LIMIT,
) -> str:
    """从文件系统读取文件，返回带行号的内容（cat -n 格式）。

    Args:
        file_path: 文件路径（相对或绝对）。
        offset: 从第几行开始读（0-indexed，默认 0）。
        limit: 最多读取行数（默认 2000）。

    Returns:
        带行号的文件内容字符串，或错误信息。
    """
    backend = _backend(ctx)
    result = await backend.aread(file_path, offset, limit)

    if not result.startswith("Error"):
        # 更新 FileStateTracker：记录读取时的文件状态
        try:
            resolved = backend._resolve_path(file_path)  # type: ignore[attr-defined]
            mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
        except (AttributeError, OSError):
            try:
                mtime = Path(file_path).stat().st_mtime
            except OSError:
                mtime = 0.0

        # offset=0 且 limit=DEFAULT 视为完整读，传 None；否则保留实际值
        tracker_offset = offset if offset != 0 else None
        tracker_limit = limit if limit != _DEFAULT_LIMIT else None
        ctx.deps.file_state_tracker.on_read(
            file_path, result, mtime, tracker_offset, tracker_limit
        )

    return result


async def edit(
    ctx: RunContext[AgentDeps],
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """通过字符串替换编辑文件。

    Args:
        file_path: 文件路径。
        old_string: 要替换的原始字符串（必须唯一，除非 replace_all=True）。
        new_string: 替换后的新字符串。
        replace_all: True 时替换所有匹配，False 时要求唯一匹配。

    Returns:
        成功时返回替换摘要，失败时返回错误信息。
    """
    backend = _backend(ctx)
    result = await backend.aedit(file_path, old_string, new_string, replace_all)

    if result.error:
        return result.error

    # 写入成功后更新 FileStateTracker
    try:
        resolved = backend._resolve_path(file_path)  # type: ignore[attr-defined]
        new_content = resolved.read_text(encoding="utf-8")
        mtime = resolved.stat().st_mtime
    except (AttributeError, OSError):
        try:
            p = Path(file_path)
            new_content = p.read_text(encoding="utf-8")
            mtime = p.stat().st_mtime
        except OSError:
            new_content = new_string
            mtime = 0.0

    ctx.deps.file_state_tracker.on_write(file_path, new_content, mtime)
    return f"已替换 {result.occurrences} 处"


async def write(
    ctx: RunContext[AgentDeps],
    file_path: str,
    content: str,
) -> str:
    """创建新文件或覆盖写入已有文件。

    注意：对于已有文件，应先用 read 读取后再写入（与 Claude Code 规范一致）。

    Args:
        file_path: 文件路径。
        content: 文件完整内容。

    Returns:
        成功消息或错误信息。
    """
    backend = _backend(ctx)
    result = await backend.awrite(file_path, content)

    if result.error:
        return result.error

    # 写入成功后更新 FileStateTracker
    try:
        resolved = backend._resolve_path(file_path)  # type: ignore[attr-defined]
        mtime = resolved.stat().st_mtime
    except (AttributeError, OSError):
        try:
            mtime = Path(file_path).stat().st_mtime
        except OSError:
            mtime = 0.0

    ctx.deps.file_state_tracker.on_write(file_path, content, mtime)
    return f"已写入 {file_path}"


async def glob(
    ctx: RunContext[AgentDeps],
    pattern: str,
    path: str = "/",
) -> str:
    """按 glob 模式查找文件，返回匹配的文件路径列表。

    Args:
        pattern: glob 模式（如 "**/*.py"、"src/**/*.ts"）。
        path: 搜索根目录（默认 "/"，即后端根目录）。

    Returns:
        换行分隔的文件路径字符串，或 "无匹配文件"。
    """
    backend = _backend(ctx)
    files = await backend.aglob_info(pattern, path)

    if not files:
        return "无匹配文件"

    return "\n".join(f["path"] for f in files)


async def grep(
    ctx: RunContext[AgentDeps],
    pattern: str,
    path: str | None = None,
    glob_pattern: str | None = None,
) -> str:
    """在文件内容中搜索字符串（固定字符串模式，非正则）。

    Args:
        pattern: 要搜索的字符串。
        path: 搜索路径（文件或目录），None 时搜索整个后端根目录。
        glob_pattern: 文件名过滤 glob（如 "*.py"），None 时搜索所有文件。

    Returns:
        匹配行列表（格式: "path:line: text"），或 "无匹配"，或错误信息。
    """
    backend = _backend(ctx)
    matches = await backend.agrep_raw(pattern, path, glob_pattern)

    if isinstance(matches, str):
        return matches  # 错误信息直接返回

    if not matches:
        return "无匹配"

    lines = [f"{m['path']}:{m['line']}: {m['text']}" for m in matches]
    return "\n".join(lines)

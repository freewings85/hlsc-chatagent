"""文件系统工具集成测试。

使用 FilesystemBackend(tmp_path) 做真实文件 I/O 测试，
通过 FunctionModel 的工具调用机制验证工具签名和返回值格式。

测试策略：直接调用工具函数（注入 mock RunContext），
不走完整 Agent Loop，以提升速度和隔离性。
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.agent.deps import AgentDeps
from src.agent.file_state import FileStateTracker
from src.agent.tools.fs import edit, glob, grep, read, write
from src.agent.tools import create_default_tool_map
from src.common.filesystem_backend import EditResult, WriteResult
from src.storage.local_backend import FilesystemBackend


# ---------------------------------------------------------------------------
# 无 _resolve_path 的 mock backend（触发 AttributeError fallback）
# ---------------------------------------------------------------------------

class _NoResolveMockBackend:
    """不含 _resolve_path 方法的 mock backend，用于触发 fs.py fallback 路径。"""

    def __init__(
        self,
        read_content: str = "  1\ttest\n",
        edit_occurrences: int = 1,
        write_error: str | None = None,
        grep_result: list | str = "Error: grep failed",
    ) -> None:
        self._read_content: str = read_content
        self._edit_result: EditResult = EditResult(error=None, occurrences=edit_occurrences)
        self._write_result: WriteResult = WriteResult(error=write_error)
        self._grep_result: list | str = grep_result

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return self._read_content

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self._edit_result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self._write_result

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list | str:
        return self._grep_result

    # 故意不定义 _resolve_path → 访问时抛出 AttributeError


def _make_ctx_no_resolve(
    read_content: str = "  1\ttest\n",
    grep_result: list | str = "Error: grep failed",
) -> Any:
    """创建使用无 _resolve_path backend 的 mock RunContext。"""
    backend: Any = _NoResolveMockBackend(
        read_content=read_content,
        grep_result=grep_result,
    )
    deps: AgentDeps = AgentDeps(backend=backend, file_state_tracker=FileStateTracker())
    ctx: Any = MagicMock()
    ctx.deps = deps
    return ctx


def make_ctx(tmp_path: Path) -> Any:
    """创建携带 FilesystemBackend 的 mock RunContext。"""
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    deps = AgentDeps(
        backend=backend,
        file_state_tracker=FileStateTracker(),
    )
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


class TestReadTool:
    @pytest.mark.asyncio
    async def test_read_returns_line_numbers(self, tmp_path: Path) -> None:
        """read 返回带行号的内容（cat -n 格式）"""
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3")

        ctx = make_ctx(tmp_path)
        result = await read(ctx, str(f))

        assert "1" in result
        assert "line1" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_read_updates_file_state_tracker(self, tmp_path: Path) -> None:
        """read 后 FileStateTracker 记录了文件 entry"""
        f = tmp_path / "tracked.py"
        f.write_text("x = 1\n")

        ctx = make_ctx(tmp_path)
        await read(ctx, str(f))

        tracker = ctx.deps.file_state_tracker
        assert len(tracker) == 1

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        """读取不存在的文件返回错误信息"""
        ctx = make_ctx(tmp_path)
        result = await read(ctx, str(tmp_path / "no_such.txt"))
        assert "Error" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_with_offset_marks_partial(self, tmp_path: Path) -> None:
        """指定 offset 时 tracker 记录 offset 值（局部读）"""
        f = tmp_path / "big.txt"
        f.write_text("\n".join(f"line{i}" for i in range(100)))

        ctx = make_ctx(tmp_path)
        await read(ctx, str(f), offset=10, limit=20)

        # 有 entry 存在
        assert len(ctx.deps.file_state_tracker) == 1
        # get_changed_files 应跳过这个局部读的 entry
        changed = ctx.deps.file_state_tracker.get_changed_files()
        assert len(changed) == 0


class TestEditTool:
    @pytest.mark.asyncio
    async def test_edit_replaces_string(self, tmp_path: Path) -> None:
        """edit 替换唯一字符串"""
        f = tmp_path / "code.py"
        f.write_text("x = 1\ny = 2\n")

        ctx = make_ctx(tmp_path)
        result = await edit(ctx, str(f), "x = 1", "x = 42")

        assert "已替换" in result
        assert f.read_text() == "x = 42\ny = 2\n"

    @pytest.mark.asyncio
    async def test_edit_updates_tracker(self, tmp_path: Path) -> None:
        """edit 成功后 tracker 记录写入状态（offset=None, limit=None）"""
        f = tmp_path / "config.yaml"
        f.write_text("version: 1\nname: test\n")

        ctx = make_ctx(tmp_path)
        await edit(ctx, str(f), "version: 1", "version: 2")

        tracker = ctx.deps.file_state_tracker
        assert len(tracker) == 1

    @pytest.mark.asyncio
    async def test_edit_nonunique_fails(self, tmp_path: Path) -> None:
        """非唯一匹配且 replace_all=False 时返回错误"""
        f = tmp_path / "dup.txt"
        f.write_text("foo\nfoo\nbar\n")

        ctx = make_ctx(tmp_path)
        result = await edit(ctx, str(f), "foo", "baz", replace_all=False)

        assert "Error" in result or "foo" in f.read_text()  # 要么报错要么文件未变

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, tmp_path: Path) -> None:
        """replace_all=True 替换全部匹配"""
        f = tmp_path / "multi.txt"
        f.write_text("foo\nfoo\nbar\n")

        ctx = make_ctx(tmp_path)
        result = await edit(ctx, str(f), "foo", "baz", replace_all=True)

        assert "已替换" in result
        assert f.read_text() == "baz\nbaz\nbar\n"


class TestWriteTool:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path: Path) -> None:
        """write 创建新文件"""
        target = tmp_path / "new_file.txt"
        ctx = make_ctx(tmp_path)

        result = await write(ctx, str(target), "hello world\n")

        assert "已写入" in result
        assert target.exists()
        assert target.read_text() == "hello world\n"

    @pytest.mark.asyncio
    async def test_write_updates_tracker(self, tmp_path: Path) -> None:
        """write 后 tracker 记录写入状态"""
        target = tmp_path / "tracked_write.py"
        ctx = make_ctx(tmp_path)

        await write(ctx, str(target), "print('hi')\n")

        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_write_existing_file_fails(self, tmp_path: Path) -> None:
        """write 到已存在文件时 FilesystemBackend 返回错误（需先 read）"""
        existing = tmp_path / "exists.txt"
        existing.write_text("old content\n")

        ctx = make_ctx(tmp_path)
        result = await write(ctx, str(existing), "new content\n")

        # FilesystemBackend.write() 对已存在文件返回错误
        assert "already exists" in result or "Error" in result


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_pattern_matching(self, tmp_path: Path) -> None:
        """glob 返回匹配的文件路径"""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        ctx = make_ctx(tmp_path)
        result = await glob(ctx, "*.py", str(tmp_path))

        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    @pytest.mark.asyncio
    async def test_glob_no_match(self, tmp_path: Path) -> None:
        """无匹配时返回提示"""
        ctx = make_ctx(tmp_path)
        result = await glob(ctx, "*.nonexistent", str(tmp_path))
        assert "无匹配" in result


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_finds_content(self, tmp_path: Path) -> None:
        """grep 找到关键字并返回 path:line: text 格式"""
        f = tmp_path / "source.py"
        f.write_text("def hello():\n    pass\n\ndef world():\n    pass\n")

        ctx = make_ctx(tmp_path)
        result = await grep(ctx, "def hello", path=str(tmp_path))

        assert "source.py" in result
        assert "def hello" in result

    @pytest.mark.asyncio
    async def test_grep_no_match(self, tmp_path: Path) -> None:
        """无匹配时返回提示"""
        f = tmp_path / "empty.py"
        f.write_text("x = 1\n")

        ctx = make_ctx(tmp_path)
        result = await grep(ctx, "NONEXISTENT_PATTERN_XYZ", path=str(tmp_path))

        assert "无匹配" in result

    @pytest.mark.asyncio
    async def test_grep_with_glob_filter(self, tmp_path: Path) -> None:
        """glob 过滤器只搜索匹配的文件"""
        (tmp_path / "a.py").write_text("FIND_ME\n")
        (tmp_path / "b.txt").write_text("FIND_ME\n")

        ctx = make_ctx(tmp_path)
        result = await grep(ctx, "FIND_ME", path=str(tmp_path), glob_pattern="*.py")

        assert "a.py" in result
        # b.txt 不应出现（glob 过滤掉了）
        assert "b.txt" not in result


class TestFileStateTrackerIntegration:
    @pytest.mark.asyncio
    async def test_changed_files_detected(self, tmp_path: Path) -> None:
        """外部修改文件后 get_changed_files() 能检测到"""
        f = tmp_path / "watched.py"
        f.write_text("version = 1\n")

        ctx = make_ctx(tmp_path)
        await read(ctx, str(f))  # 记录初始状态

        # 模拟外部修改（修改文件内容，触发 mtime 变化）
        import time
        time.sleep(0.01)
        f.write_text("version = 2\n")

        changed = ctx.deps.file_state_tracker.get_changed_files()
        assert len(changed) == 1
        assert changed[0].path == str(f)

    @pytest.mark.asyncio
    async def test_write_tool_no_false_changed(self, tmp_path: Path) -> None:
        """write 工具写入后不应被误判为 changed_file"""
        target = tmp_path / "output.py"
        ctx = make_ctx(tmp_path)

        await write(ctx, str(target), "result = 42\n")

        # 刚写入后，mtime 与 tracker 记录一致，不应报 changed
        changed = ctx.deps.file_state_tracker.get_changed_files()
        assert len(changed) == 0

    def test_clear_resets_tracker(self, tmp_path: Path) -> None:
        """clear() 后 tracker 为空"""
        tracker = FileStateTracker()
        tracker.on_read("/some/file.py", "content", 1234.0, None, None)
        assert len(tracker) == 1

        tracker.clear()
        assert len(tracker) == 0


class TestFsToolsFallbackPaths:
    """US-001: backend 无 _resolve_path 时触发 AttributeError fallback 路径（fs.py 56-60, 101-108, 140-144, 193）"""

    @pytest.mark.asyncio
    async def test_read_fallback_file_exists(self, tmp_path: Path) -> None:
        """read: _resolve_path AttributeError → fallback Path().stat() 成功（覆盖 56-59 行）"""
        f: Path = tmp_path / "test.py"
        f.write_text("test content\n")

        ctx: Any = _make_ctx_no_resolve()
        result: str = await read(ctx, str(f))

        assert result == "  1\ttest\n"
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_read_fallback_file_not_exists(self, tmp_path: Path) -> None:
        """read: _resolve_path AttributeError → fallback Path().stat() OSError → mtime=0.0（覆盖 56-60 行）"""
        nonexistent: Path = tmp_path / "ghost.py"

        ctx: Any = _make_ctx_no_resolve()
        result: str = await read(ctx, str(nonexistent))

        assert result == "  1\ttest\n"
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_edit_fallback_file_exists(self, tmp_path: Path) -> None:
        """edit: _resolve_path AttributeError → fallback Path().read_text() 成功（覆盖 101-105 行）"""
        f: Path = tmp_path / "code.py"
        f.write_text("x = 42\n")

        ctx: Any = _make_ctx_no_resolve()
        result: str = await edit(ctx, str(f), "x = 1", "x = 42")

        assert "已替换" in result
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_edit_fallback_file_not_exists(self, tmp_path: Path) -> None:
        """edit: _resolve_path AttributeError + Path().read_text() OSError → new_content=new_string（覆盖 101-108 行）"""
        nonexistent: Path = tmp_path / "ghost.py"

        ctx: Any = _make_ctx_no_resolve()
        result: str = await edit(ctx, str(nonexistent), "old", "new")

        assert "已替换" in result
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_write_fallback_file_exists(self, tmp_path: Path) -> None:
        """write: _resolve_path AttributeError → fallback Path().stat() 成功（覆盖 140-142 行）"""
        f: Path = tmp_path / "out.py"
        f.write_text("content\n")

        ctx: Any = _make_ctx_no_resolve()
        result: str = await write(ctx, str(f), "content\n")

        assert "已写入" in result
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_write_fallback_file_not_exists(self, tmp_path: Path) -> None:
        """write: _resolve_path AttributeError + Path().stat() OSError → mtime=0.0（覆盖 140-144 行）"""
        nonexistent: Path = tmp_path / "ghost.py"

        ctx: Any = _make_ctx_no_resolve()
        result: str = await write(ctx, str(nonexistent), "content\n")

        assert "已写入" in result
        assert len(ctx.deps.file_state_tracker) == 1

    @pytest.mark.asyncio
    async def test_grep_returns_str_error_message(self, tmp_path: Path) -> None:
        """grep: agrep_raw 返回 str（错误消息）时直接返回（覆盖 fs.py 193 行）"""
        ctx: Any = _make_ctx_no_resolve(grep_result="Error: grep failed")
        result: str = await grep(ctx, "pattern")

        assert result == "Error: grep failed"


class TestFileStateTrackerOSErrorPath:
    """US-003: file_state.py get_changed_files() 中文件被删除时的 OSError 路径（91-92 行）"""

    def test_get_changed_files_file_not_on_disk(self) -> None:
        """on_read 后文件从磁盘删除，get_changed_files() 跳过该文件（OSError → continue）"""
        tracker: FileStateTracker = FileStateTracker()
        # 记录一个不存在的路径
        tracker.on_read("/nonexistent/path/file.py", "content", 0.0, None, None)

        changed: list = tracker.get_changed_files()
        # 文件不存在 → OSError → continue → 不返回
        assert len(changed) == 0

    def test_get_changed_files_file_not_modified(self, tmp_path: Path) -> None:
        """on_read 后文件未被修改，get_changed_files() 返回空列表"""
        f: Path = tmp_path / "stable.py"
        f.write_text("x = 1\n")
        mtime: float = f.stat().st_mtime

        tracker: FileStateTracker = FileStateTracker()
        tracker.on_read(str(f), "x = 1\n", mtime, None, None)

        changed: list = tracker.get_changed_files()
        assert len(changed) == 0


class TestCreateDefaultToolMap:
    """agent/tools/__init__.py create_default_tool_map 覆盖（第 38 行）"""

    def test_create_default_tool_map_returns_all_tools(self) -> None:
        """create_default_tool_map() 返回包含所有工具的 dict"""
        tool_map: dict = create_default_tool_map()

        assert "read" in tool_map
        assert "edit" in tool_map
        assert "write" in tool_map
        assert "glob" in tool_map
        assert "grep" in tool_map
        assert "bash" in tool_map
        assert "task" in tool_map
        assert "ask_user" in tool_map
        assert len(tool_map) == 8

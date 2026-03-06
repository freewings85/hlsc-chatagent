"""FilesystemBackend 测试"""

import pytest

from src.storage.local_backend import FilesystemBackend


class TestFilesystemBackend:

    def test_read_write(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        result = backend.write("/test.txt", "hello world")
        assert result.error is None
        assert result.path == "/test.txt"

        content = backend.read("/test.txt")
        assert "hello world" in content

    def test_read_not_found(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        content = backend.read("/nonexistent.txt")
        assert "Error" in content

    def test_edit(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        backend.write("/test.txt", "hello world")

        result = backend.edit("/test.txt", "hello", "goodbye")
        assert result.error is None
        assert result.occurrences == 1

        content = backend.read("/test.txt")
        assert "goodbye world" in content

    def test_exists(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        assert not backend.exists("/test.txt")

        backend.write("/test.txt", "content")
        assert backend.exists("/test.txt")

    def test_delete(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        backend.write("/test.txt", "content")
        assert backend.exists("/test.txt")

        assert backend.delete("/test.txt")
        assert not backend.exists("/test.txt")

    def test_ls_info(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        backend.write("/dir/a.txt", "aaa")
        backend.write("/dir/b.txt", "bbb")

        items = backend.ls_info("/dir")
        paths = [i["path"] for i in items]
        assert "/dir/a.txt" in paths
        assert "/dir/b.txt" in paths

    def test_virtual_mode_blocks_traversal(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with pytest.raises(ValueError, match="traversal"):
            backend.read("/../etc/passwd")

    @pytest.mark.asyncio
    async def test_async_read_write(self, tmp_path) -> None:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        await backend.awrite("/async.txt", "async content")
        content = await backend.aread("/async.txt")
        assert "async content" in content

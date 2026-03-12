"""FilesystemBackend 测试"""

import asyncio

import pytest

from src.sdk._storage.local_backend import FilesystemBackend


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

    def test_delete_root_refused(self, tmp_path) -> None:
        """delete('/') 不能删除根目录"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        # 先写入一个文件确认数据存在
        backend.write("/test.txt", "data")
        assert backend.exists("/test.txt")

        # 尝试删除根目录应该返回 False
        result = backend.delete("/")
        assert result is False

        # 数据应该仍然存在
        assert backend.exists("/test.txt")

    @pytest.mark.asyncio
    async def test_concurrent_aedit_same_file(self, tmp_path) -> None:
        """并发 aedit 同一文件时，所有修改都应保留（不丢失）。

        模拟 plan.md 场景：5 个 checkbox 并发更新。
        """
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        backend.write("/plan.md", (
            "# 任务计划\n"
            "- [ ] 步骤 1: 做事A\n"
            "- [ ] 步骤 2: 做事B\n"
            "- [ ] 步骤 3: 做事C\n"
            "- [ ] 步骤 4: 做事D\n"
            "- [ ] 步骤 5: 做事E\n"
            "## 状态\n"
            "进行中\n"
        ))

        # 并发编辑 5 个 checkbox
        results = await asyncio.gather(
            backend.aedit("/plan.md", "- [ ] 步骤 1: 做事A", "- [x] 步骤 1: 做事A"),
            backend.aedit("/plan.md", "- [ ] 步骤 2: 做事B", "- [x] 步骤 2: 做事B"),
            backend.aedit("/plan.md", "- [ ] 步骤 3: 做事C", "- [x] 步骤 3: 做事C"),
            backend.aedit("/plan.md", "- [ ] 步骤 4: 做事D", "- [x] 步骤 4: 做事D"),
            backend.aedit("/plan.md", "- [ ] 步骤 5: 做事E", "- [x] 步骤 5: 做事E"),
        )

        # 所有编辑应成功
        for r in results:
            assert r.error is None, f"Edit failed: {r.error}"

        # 所有 checkbox 都应该被标记为完成
        content = backend.read("/plan.md")
        assert "- [x] 步骤 1" in content
        assert "- [x] 步骤 2" in content
        assert "- [x] 步骤 3" in content
        assert "- [x] 步骤 4" in content
        assert "- [x] 步骤 5" in content
        assert "- [ ]" not in content  # 不应有未完成的

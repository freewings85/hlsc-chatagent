"""InvokedSkillStore 测试"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.agent.skills.invoked_store import InvokedSkill, InvokedSkillStore, _invoked_skills_path
from src.storage.local_backend import FilesystemBackend


def make_backend(tmp_path: Path) -> FilesystemBackend:
    """创建共享 backend（virtual_mode=True，in-memory，需多个 Store 实例共用同一 backend）。"""
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


def make_store(
    backend: FilesystemBackend,
    user_id: str = "u1",
    session_id: str = "s1",
) -> InvokedSkillStore:
    return InvokedSkillStore(backend, user_id, session_id)


def make_skill(name: str = "commit", content: str = "# Commit\n") -> InvokedSkill:
    return InvokedSkill(
        name=name,
        content=content,
        invoked_at=datetime(2026, 3, 7, 10, 0, 0, tzinfo=timezone.utc),
    )


class TestInvokedSkillStorePath:
    def test_path_format(self) -> None:
        """session 文件路径格式正确"""
        path = _invoked_skills_path("user123", "session456")
        assert path == "/user123/sessions/session456/invoked_skills.json"


class TestInvokedSkillStoreLoad:
    async def test_load_empty_when_no_file(self, tmp_path: Path) -> None:
        """文件不存在时 load 后 get_all 返回空字典"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.load()
        assert store.get_all() == {}

    async def test_load_restores_records(self, tmp_path: Path) -> None:
        """load 后能恢复已记录的 skill（共用同一 backend 模拟进程重启）"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        skill = make_skill("commit", "# Commit")
        await store.record(skill)

        # 共用同一 backend 实例，新建 store 模拟进程重启后重新加载
        store2 = make_store(backend)
        await store2.load()

        all_skills = store2.get_all()
        assert "commit" in all_skills
        assert all_skills["commit"].name == "commit"
        assert all_skills["commit"].content == "# Commit"

    async def test_load_handles_corrupted_file(self, tmp_path: Path) -> None:
        """损坏的 JSON 文件时 load 静默跳过，返回空字典"""
        backend = make_backend(tmp_path)
        path = _invoked_skills_path("u1", "s1")
        await backend.awrite(path, "not valid json {{{")

        store = InvokedSkillStore(backend, "u1", "s1")
        await store.load()  # 不应该抛异常
        assert store.get_all() == {}


class TestInvokedSkillStoreRecord:
    async def test_record_stores_in_memory(self, tmp_path: Path) -> None:
        """record 后 get_all 立即可见"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        skill = make_skill("commit")
        await store.record(skill)

        all_skills = store.get_all()
        assert "commit" in all_skills
        assert all_skills["commit"].name == "commit"

    async def test_record_persists_to_file(self, tmp_path: Path) -> None:
        """record 后文件已写入"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")
        await store.record(make_skill("commit"))

        raw = await backend.aread(_invoked_skills_path("u1", "s1"))
        assert raw is not None
        assert "commit" in raw

    async def test_record_upsert_overwrites_same_name(self, tmp_path: Path) -> None:
        """同名 skill 重复 record 时覆盖（upsert）"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.record(InvokedSkill("commit", "v1", datetime(2026, 1, 1, tzinfo=timezone.utc)))
        await store.record(InvokedSkill("commit", "v2", datetime(2026, 2, 1, tzinfo=timezone.utc)))

        all_skills = store.get_all()
        assert all_skills["commit"].content == "v2"

    async def test_record_multiple_skills(self, tmp_path: Path) -> None:
        """record 多个不同 skill"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.record(make_skill("commit", "# Commit"))
        await store.record(make_skill("review", "# Review"))

        all_skills = store.get_all()
        assert len(all_skills) == 2
        assert "commit" in all_skills
        assert "review" in all_skills


class TestInvokedSkillStoreGetAll:
    async def test_get_all_returns_copy(self, tmp_path: Path) -> None:
        """get_all 返回字典副本，修改不影响内部状态"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.record(make_skill("commit"))

        result = store.get_all()
        result.clear()  # 修改副本

        # 内部状态不受影响
        assert "commit" in store.get_all()

    async def test_get_all_empty_before_load(self, tmp_path: Path) -> None:
        """未 load 前 get_all 返回空字典"""
        backend = make_backend(tmp_path)
        store = make_store(backend)
        assert store.get_all() == {}


class TestInvokedSkillStoreRoundTrip:
    async def test_datetime_preserved_across_load(self, tmp_path: Path) -> None:
        """invoked_at datetime 在序列化/反序列化后保持一致"""
        dt = datetime(2026, 3, 7, 12, 30, 45, tzinfo=timezone.utc)
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.record(InvokedSkill("commit", "# Commit", dt))

        store2 = make_store(backend)
        await store2.load()

        loaded = store2.get_all()["commit"]
        assert loaded.invoked_at == dt

    async def test_content_with_special_chars_preserved(self, tmp_path: Path) -> None:
        """包含特殊字符（中文、换行、引号）的内容序列化后不损坏"""
        content = '# 提交\n步骤1: git status\n步骤2: "git add"'
        backend = make_backend(tmp_path)
        store = make_store(backend)
        await store.record(make_skill("commit", content))

        store2 = make_store(backend)
        await store2.load()
        assert store2.get_all()["commit"].content == content

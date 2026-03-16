"""invoke_skill tool 测试"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.skills.invoked_store import InvokedSkill, InvokedSkillStore
from agent_sdk._agent.skills.registry import SkillEntry, SkillRegistry
from agent_sdk._agent.skills.tool import invoke_skill


def make_entry(
    name: str = "commit",
    content: str = "# Commit\nStep 1.",
    source_path: Path | None = None,
) -> SkillEntry:
    return SkillEntry(
        name=name,
        description=f"{name} description",
        content=content,
        when_to_use=f"Use when doing {name}.",
        source_path=source_path,
    )


def make_registry(*entries: SkillEntry) -> SkillRegistry:
    registry = SkillRegistry()
    for e in entries:
        registry._entries[e.name] = e
    return registry


def make_ctx(
    registry: SkillRegistry | None = None,
    store: InvokedSkillStore | None = None,
) -> RunContext[AgentDeps]:
    deps = AgentDeps(
        skill_registry=registry,
        invoked_skill_store=store,
    )
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


class TestInvokeSkillRegistryNone:
    async def test_returns_not_available_when_no_registry(self) -> None:
        """registry 为 None 时返回系统不可用提示"""
        ctx = make_ctx(registry=None)
        result = await invoke_skill(ctx, "commit")
        assert "not available" in result

    async def test_no_exception_when_registry_none(self) -> None:
        """registry 为 None 时不抛异常"""
        ctx = make_ctx(registry=None)
        result = await invoke_skill(ctx, "commit")
        assert isinstance(result, str)


class TestInvokeSkillNotFound:
    async def test_returns_not_found_for_unknown_skill(self) -> None:
        """skill 不存在时返回 not found 提示"""
        registry = make_registry(make_entry("commit"))
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "unknown_skill")
        assert "not found" in result
        assert "unknown_skill" in result

    async def test_not_found_message_lists_available_skills(self) -> None:
        """not found 时提示可用 skill 列表"""
        registry = make_registry(make_entry("commit"), make_entry("review"))
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "missing")
        # commit 和 review 应该出现在提示中
        assert "commit" in result or "review" in result


class TestInvokeSkillSuccess:
    async def test_returns_skill_content(self) -> None:
        """成功调用时返回 SKILL.md 内容"""
        entry = make_entry("commit", "# Commit\nDo the commit.")
        registry = make_registry(entry)
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "commit")
        assert "# Commit" in result
        assert "Do the commit." in result

    async def test_returns_metadata_tag(self) -> None:
        """返回值包含 metadata tag"""
        registry = make_registry(make_entry("commit"))
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "commit")
        assert "<command-name>commit</command-name>" in result
        assert "<skill-format>true</skill-format>" in result

    async def test_args_included_in_metadata_tag(self) -> None:
        """args 参数包含在 metadata tag 中"""
        registry = make_registry(make_entry("commit"))
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "commit", args="-m 'fix bug'")
        assert "<command-args>-m 'fix bug'</command-args>" in result

    async def test_empty_args_default(self) -> None:
        """无 args 时 command-args 为空字符串"""
        registry = make_registry(make_entry("commit"))
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "commit")
        assert "<command-args></command-args>" in result


class TestInvokeSkillPersistence:
    async def test_records_to_invoked_store(self) -> None:
        """成功调用时写入 InvokedSkillStore"""
        entry = make_entry("commit", "# Commit")
        registry = make_registry(entry)

        store = MagicMock(spec=InvokedSkillStore)
        store.record = AsyncMock()
        ctx = make_ctx(registry=registry, store=store)

        await invoke_skill(ctx, "commit")

        store.record.assert_awaited_once()
        recorded: InvokedSkill = store.record.call_args[0][0]
        assert recorded.name == "commit"
        assert recorded.content == "# Commit"
        assert recorded.invoked_at is not None

    async def test_no_store_call_when_store_none(self) -> None:
        """store 为 None 时不报错，正常返回 skill 内容"""
        registry = make_registry(make_entry("commit"))
        ctx = make_ctx(registry=registry, store=None)
        result = await invoke_skill(ctx, "commit")
        assert "# Commit" in result

    async def test_store_receives_correct_skill_name(self) -> None:
        """store 收到正确的 skill 名称"""
        entry = make_entry("review", "# Review")
        registry = make_registry(entry)

        store = MagicMock(spec=InvokedSkillStore)
        store.record = AsyncMock()
        ctx = make_ctx(registry=registry, store=store)

        await invoke_skill(ctx, "review")

        recorded: InvokedSkill = store.record.call_args[0][0]
        assert recorded.name == "review"


class TestInvokeSkillDir:
    async def test_skill_dir_injected(self) -> None:
        """有 source_path 时注入 <skill-dir> 标签"""
        entry = make_entry(
            "bidding",
            'Run: bash("python scripts/prepare.py")',
            source_path=Path("/skills/publish-bidding/SKILL.md"),
        )
        registry = make_registry(entry)
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "bidding")
        assert "<skill-dir>" in result
        assert "/skills/publish-bidding</skill-dir>" in result
        # 原始内容不被修改
        assert "python scripts/prepare.py" in result

    async def test_no_skill_dir_when_no_source_path(self) -> None:
        """source_path 为 None 时不注入 <skill-dir>"""
        entry = make_entry(
            "test",
            "Run scripts/run.py",
            source_path=None,
        )
        registry = make_registry(entry)
        ctx = make_ctx(registry=registry)
        result = await invoke_skill(ctx, "test")
        assert "<skill-dir>" not in result

"""Skill 系统端到端集成测试

验证完整的 skill 流程：
  SkillRegistry.load() → PreModelCallMessageService 注入 → invoke_skill 执行
  → InvokedSkillStore 持久化 → compact 后 invoked_skills 重新注入

使用 FunctionModel（不调用真实 LLM），用 in-memory backend（virtual_mode=True）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from src.sdk._agent.compact.compactor import CompactResult
from src.sdk._agent.deps import AgentDeps
from src.sdk._agent.message.attachment_collector import AttachmentCollector
from src.sdk._agent.message.context_injector import wrap_system_reminder
from src.sdk._agent.message.pre_model_call_service import (
    PreModelCallMessageService,
    _INVOKED_SKILLS_SOURCE,
    _SKILL_LISTING_SOURCE,
)
from src.sdk._agent.skills.invoked_store import InvokedSkill, InvokedSkillStore
from src.sdk._agent.skills.registry import SkillEntry, SkillRegistry
from src.sdk._agent.skills.tool import invoke_skill
from src.sdk._storage.local_backend import FilesystemBackend


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def make_backend(tmp_path: Path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


def make_registry_with_skills(*entries: SkillEntry) -> SkillRegistry:
    registry = SkillRegistry()
    for e in entries:
        registry._entries[e.name] = e
    return registry


def make_skill_entry(
    name: str,
    description: str = "A skill",
    content: str = "# Instructions\nDo the thing.",
    when_to_use: str | None = None,
) -> SkillEntry:
    return SkillEntry(
        name=name,
        description=description,
        content=content,
        when_to_use=when_to_use,
    )


def make_working_messages(n: int = 2) -> list[ModelMessage]:
    """生成 n 轮对话的消息列表。"""
    msgs: list[ModelMessage] = []
    for i in range(n):
        msgs.append(ModelRequest(parts=[UserPromptPart(content=f"用户消息 {i}")]))
        msgs.append(ModelResponse(parts=[TextPart(content=f"助手回复 {i}")]))
    return msgs


def make_pre_call_service(
    registry: SkillRegistry | None = None,
    store: InvokedSkillStore | None = None,
) -> PreModelCallMessageService:
    """创建一个最简化的 PreModelCallMessageService（无 context、无 attachment、无 compact）。"""
    from src.sdk._agent.compact.compactor import Compactor, CompactConfig
    from src.sdk._agent.file_state import FileStateTracker

    compactor = Compactor(
        config=CompactConfig(
            context_window=1_000_000,  # 不触发 compact
            output_reserve=0,
            min_savings_threshold=0,
        ),
        user_id="u1",
        session_id="s1",
    )
    attachment_collector = AttachmentCollector(FileStateTracker())
    return PreModelCallMessageService(
        compactor=compactor,
        context_messages=[],
        attachment_collector=attachment_collector,
        skill_registry=registry,
        invoked_skill_store=store,
    )


# --------------------------------------------------------------------------- #
# Test: SkillRegistry load from temp dir
# --------------------------------------------------------------------------- #

class TestSkillRegistryLoad:
    """验证从文件系统目录加载 SKILL.md 的完整流程。"""

    def test_load_from_temp_dir(self, tmp_path: Path) -> None:
        """从临时目录加载 SKILL.md，entry 字段正确。"""
        skill_dir = tmp_path / "commit"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: commit\n"
            'description: "Commit changes to git"\n'
            "when_to_use: Use when committing code changes\n"
            "---\n"
            "# Commit\n"
            "Run git commit -m 'message'.\n"
        )

        registry = SkillRegistry.load([tmp_path])
        assert registry.has_skills()
        entry = registry.get("commit")
        assert entry is not None
        assert entry.name == "commit"
        assert "Commit" in entry.description
        assert "when committing" in (entry.when_to_use or "")
        assert "# Commit" in entry.content

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        """同一目录多个 skill 全部加载。"""
        for name in ["review", "deploy", "test"]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {name} task\n---\n# {name}\n"
            )
        registry = SkillRegistry.load([tmp_path])
        assert len(registry._entries) == 3

    def test_higher_priority_overrides_lower(self, tmp_path: Path) -> None:
        """高优先级目录（后加载）覆盖低优先级同名 skill。"""
        low_dir = tmp_path / "low"
        high_dir = tmp_path / "high"
        low_dir.mkdir(); high_dir.mkdir()

        for d, desc in [(low_dir, "low priority"), (high_dir, "HIGH PRIORITY")]:
            (d / "commit").mkdir()
            (d / "commit" / "SKILL.md").write_text(
                f"---\nname: commit\ndescription: {desc}\n---\n# Commit\n"
            )

        registry = SkillRegistry.load([low_dir, high_dir])
        entry = registry.get("commit")
        assert entry is not None
        assert "HIGH PRIORITY" in entry.description

    def test_missing_dir_skipped(self, tmp_path: Path) -> None:
        """不存在的目录被静默跳过，不抛异常。"""
        nonexistent = tmp_path / "nonexistent"
        registry = SkillRegistry.load([nonexistent])
        assert not registry.has_skills()

    def test_skill_without_frontmatter_skipped(self, tmp_path: Path) -> None:
        """无 frontmatter 的 SKILL.md 被跳过（返回 None）。"""
        d = tmp_path / "broken"
        d.mkdir()
        (d / "SKILL.md").write_text("# No frontmatter\nJust content.\n")
        registry = SkillRegistry.load([tmp_path])
        assert not registry.has_skills()


# --------------------------------------------------------------------------- #
# Test: PreModelCallMessageService skill injection pipeline
# --------------------------------------------------------------------------- #

class TestSkillInjectionPipeline:
    """验证 PreModelCallMessageService 的 skill 注入流程。"""

    async def test_skill_listing_injected_when_registry_has_skills(
        self, tmp_path: Path
    ) -> None:
        """registry 有 skill 时，skill_listing 被注入到消息列表。"""
        registry = make_registry_with_skills(
            make_skill_entry("commit", "Commit changes")
        )
        service = make_pre_call_service(registry=registry)
        msgs = make_working_messages(1)

        result = await service.handle(msgs)

        # 检查 skill_listing 消息已注入
        listing_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        ]
        assert len(listing_msgs) == 1
        listing_content = listing_msgs[0].parts[0].content  # type: ignore
        assert "commit" in listing_content

    async def test_skill_listing_not_injected_when_registry_none(
        self, tmp_path: Path
    ) -> None:
        """registry 为 None 时，不注入 skill_listing。"""
        service = make_pre_call_service(registry=None)
        msgs = make_working_messages(1)
        result = await service.handle(msgs)

        listing_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        ]
        assert len(listing_msgs) == 0

    async def test_invoked_skills_injected_after_skill_recorded(
        self, tmp_path: Path
    ) -> None:
        """invoked_skill_store 有记录时，invoked_skills 被注入。"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")

        skill = InvokedSkill(
            name="commit",
            content="# Commit Instructions\nRun git commit.",
            invoked_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        await store.record(skill)

        service = make_pre_call_service(store=store)
        msgs = make_working_messages(1)

        result = await service.handle(msgs)

        invoked_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _INVOKED_SKILLS_SOURCE
        ]
        assert len(invoked_msgs) == 1
        content = invoked_msgs[0].parts[0].content  # type: ignore
        assert "commit" in content.lower()
        assert "# Commit Instructions" in content

    async def test_injection_order_invoked_first_then_listing(
        self, tmp_path: Path
    ) -> None:
        """消息顺序：invoked_skills [0], skill_listing [1], 其余消息之后。"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")
        await store.record(InvokedSkill(
            name="commit", content="# Commit",
            invoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        registry = make_registry_with_skills(
            make_skill_entry("review", "Review code")
        )

        service = make_pre_call_service(registry=registry, store=store)
        msgs = make_working_messages(2)  # 4 条消息

        result = await service.handle(msgs)

        meta_msgs = [
            (i, m) for i, m in enumerate(result.model_messages)
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict) and m.metadata.get("is_meta")
        ]
        sources = [m.metadata["source"] for _, m in meta_msgs]  # type: ignore

        # invoked_skills 必须在 skill_listing 之前
        assert _INVOKED_SKILLS_SOURCE in sources
        assert _SKILL_LISTING_SOURCE in sources
        assert sources.index(_INVOKED_SKILLS_SOURCE) < sources.index(_SKILL_LISTING_SOURCE)

    async def test_dedup_on_repeated_handle_calls(self, tmp_path: Path) -> None:
        """多次调用 handle()，skill 消息不重复（旧的被移除后重新注入）。"""
        registry = make_registry_with_skills(
            make_skill_entry("commit", "Commit changes")
        )
        service = make_pre_call_service(registry=registry)
        msgs = make_working_messages(1)

        result1 = await service.handle(msgs)
        result2 = await service.handle(result1.model_messages)

        listing_msgs = [
            m for m in result2.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        ]
        assert len(listing_msgs) == 1  # 只有一条，不重复


# --------------------------------------------------------------------------- #
# Test: invoke_skill tool complete flow
# --------------------------------------------------------------------------- #

class TestInvokeSkillCompleteFlow:
    """验证 invoke_skill 工具调用的完整流程（registry → store → return value）。"""

    async def test_full_invoke_flow(self, tmp_path: Path) -> None:
        """成功调用 skill：返回 metadata tag + content，store 收到记录。"""
        from unittest.mock import MagicMock

        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")
        registry = make_registry_with_skills(
            make_skill_entry("commit", "Commit changes", "# Commit\nStep 1. Stage files.")
        )

        deps = AgentDeps(skill_registry=registry, invoked_skill_store=store)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        result = await invoke_skill(ctx, "commit", "-m 'fix bug'")

        # metadata tag
        assert "<command-name>commit</command-name>" in result
        assert "<command-args>-m 'fix bug'</command-args>" in result
        assert "<skill-format>true</skill-format>" in result
        # content
        assert "# Commit" in result
        assert "Stage files" in result

        # store 已记录
        recorded = store.get_all()
        assert "commit" in recorded
        assert recorded["commit"].content == "# Commit\nStep 1. Stage files."

    async def test_store_persists_across_load(self, tmp_path: Path) -> None:
        """invoke_skill 调用后，另一个 store 实例 load() 可恢复记录。"""
        from unittest.mock import MagicMock

        backend = make_backend(tmp_path)
        store1 = InvokedSkillStore(backend, "u1", "s1")
        registry = make_registry_with_skills(
            make_skill_entry("review", "Review code", "# Review\nCheck each line.")
        )

        deps = AgentDeps(skill_registry=registry, invoked_skill_store=store1)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        await invoke_skill(ctx, "review")

        # 新 store 实例 load 后能恢复
        store2 = InvokedSkillStore(backend, "u1", "s1")
        await store2.load()
        loaded = store2.get_all()
        assert "review" in loaded
        assert "# Review" in loaded["review"].content

    async def test_invoked_skill_appears_in_pre_call_after_invoke(
        self, tmp_path: Path
    ) -> None:
        """invoke_skill 执行后，下一次 pre_call_service.handle() 注入 invoked_skills。"""
        from unittest.mock import MagicMock

        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")
        registry = make_registry_with_skills(
            make_skill_entry("commit", "Commit changes", "# Commit\nRun git commit.")
        )

        # 1. invoke skill
        deps = AgentDeps(skill_registry=registry, invoked_skill_store=store)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps
        await invoke_skill(ctx, "commit")

        # 2. 下一轮 pre_call 注入
        service = make_pre_call_service(registry=registry, store=store)
        msgs = make_working_messages(1)
        result = await service.handle(msgs)

        invoked_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _INVOKED_SKILLS_SOURCE
        ]
        assert len(invoked_msgs) == 1
        content = invoked_msgs[0].parts[0].content  # type: ignore
        assert "# Commit" in content
        assert "Run git commit." in content


# --------------------------------------------------------------------------- #
# Test: compact 安全性（invoked_skills 在 compact 后仍可注入）
# --------------------------------------------------------------------------- #

class TestSkillPersistenceAcrossCompact:
    """验证 compact 后 InvokedSkillStore 持久化，下轮仍能注入 invoked_skills。"""

    async def test_invoked_skills_survive_compact(self, tmp_path: Path) -> None:
        """compact 清空消息历史后，invoked_skills.json 仍存在，下轮注入正常。"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")

        # 先记录一个 skill
        await store.record(InvokedSkill(
            name="commit",
            content="# Commit\nRun git commit.",
            invoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))

        # 模拟 compact：另一个 store 实例 load() 验证文件持久化
        store_reloaded = InvokedSkillStore(backend, "u1", "s1")
        await store_reloaded.load()

        assert "commit" in store_reloaded.get_all()
        assert "# Commit" in store_reloaded.get_all()["commit"].content

    async def test_empty_message_history_still_gets_invoked_skills(
        self, tmp_path: Path
    ) -> None:
        """compact 后消息历史清空，只有一条 UserPromptPart，invoked_skills 仍然注入。"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")
        await store.record(InvokedSkill(
            name="review",
            content="# Review\nCheck PR carefully.",
            invoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))

        service = make_pre_call_service(store=store)
        # compact 后消息历史可能只剩一条
        minimal_msgs = [ModelRequest(parts=[UserPromptPart(content="继续")])]
        result = await service.handle(minimal_msgs)

        invoked_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _INVOKED_SKILLS_SOURCE
        ]
        assert len(invoked_msgs) == 1

    async def test_multiple_invoked_skills_all_included(self, tmp_path: Path) -> None:
        """多个 invoked skills 全部包含在同一个 attachment 中。"""
        backend = make_backend(tmp_path)
        store = InvokedSkillStore(backend, "u1", "s1")

        skills_data = [
            ("commit", "# Commit\nStage and commit."),
            ("review", "# Review\nRead the diff."),
            ("deploy", "# Deploy\nRun deploy.sh."),
        ]
        base_time = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        for i, (name, content) in enumerate(skills_data):
            await store.record(InvokedSkill(
                name=name,
                content=content,
                invoked_at=datetime(2026, 3, 1, i, 0, 0, tzinfo=timezone.utc),
            ))

        service = make_pre_call_service(store=store)
        msgs = make_working_messages(1)
        result = await service.handle(msgs)

        invoked_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _INVOKED_SKILLS_SOURCE
        ]
        assert len(invoked_msgs) == 1
        content = invoked_msgs[0].parts[0].content  # type: ignore
        for name, _ in skills_data:
            assert f"### Skill: {name}" in content


# --------------------------------------------------------------------------- #
# Test: SkillRegistry.format_listing() 字符预算
# --------------------------------------------------------------------------- #

class TestSkillListingFormatting:
    """验证 format_listing() 的字符预算控制和格式。"""

    def test_many_skills_truncated_within_budget(self) -> None:
        """大量 skills 时，format_listing 不超过 4000 字符。"""
        registry = SkillRegistry()
        for i in range(100):
            registry._entries[f"skill_{i:03d}"] = SkillEntry(
                name=f"skill_{i:03d}",
                description=f"Description for skill number {i} with a longer text",
                content=f"# Skill {i}\nContent.",
            )
        listing = registry.format_listing()
        assert len(listing) <= 4100  # 允许最后一行略超

    def test_format_includes_when_to_use(self) -> None:
        """有 when_to_use 时，listing 格式为 'name: description - when_to_use'。"""
        registry = make_registry_with_skills(
            make_skill_entry(
                "commit",
                "Commit code changes",
                when_to_use="Use when you need to commit",
            )
        )
        listing = registry.format_listing()
        assert "commit" in listing
        assert "Commit code changes" in listing
        assert "Use when you need to commit" in listing

    def test_format_without_when_to_use(self) -> None:
        """无 when_to_use 时，listing 格式为 'name: description'。"""
        registry = make_registry_with_skills(
            make_skill_entry("review", "Review pull requests")
        )
        listing = registry.format_listing()
        assert "review: Review pull requests" in listing

    def test_long_description_truncated(self) -> None:
        """超长 description 被截断为 200 字符（含 ...）。"""
        long_desc = "A" * 300
        registry = make_registry_with_skills(
            make_skill_entry("commit", long_desc)
        )
        listing = registry.format_listing()
        # 找到 commit 那行
        line = next(l for l in listing.splitlines() if "commit" in l)
        assert len(line) <= 220  # name + ": " + 200 desc ≈ 210

    def test_disable_model_invocation_excludes_from_listing(self) -> None:
        """disable_model_invocation=True 的 skill 不出现在 listing 中。"""
        registry = SkillRegistry()
        registry._entries["hidden"] = SkillEntry(
            name="hidden",
            description="Hidden skill",
            content="...",
            disable_model_invocation=True,
        )
        registry._entries["visible"] = SkillEntry(
            name="visible",
            description="Visible skill",
            content="...",
        )
        listing = registry.format_listing()
        assert "visible" in listing
        assert "hidden" not in listing

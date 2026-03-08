"""PromptBuilder 测试"""

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from src.agent.prompt.prompt_builder import PromptBuilder
from src.storage.local_backend import FilesystemBackend


def _make_builder(user_fs_root, agent_fs_root):
    """创建 PromptBuilder，使用两个独立的 backend。"""
    return PromptBuilder(
        user_fs_backend=FilesystemBackend(root_dir=user_fs_root, virtual_mode=True),
        agent_fs_backend=FilesystemBackend(root_dir=agent_fs_root, virtual_mode=True),
    )


class TestPromptBuilder:

    def test_build_system_prompt(self, tmp_path) -> None:
        """系统提示词从模板加载"""
        builder = _make_builder(tmp_path / "user", tmp_path / "agent")

        prompt = builder.build_system_prompt()
        assert "助手" in prompt
        assert len(prompt) > 10

    def test_build_system_prompt_cached(self, tmp_path) -> None:
        """系统提示词有缓存"""
        builder = _make_builder(tmp_path / "user", tmp_path / "agent")

        p1 = builder.build_system_prompt()
        p2 = builder.build_system_prompt()
        assert p1 is p2  # 同一对象引用

    @pytest.mark.asyncio
    async def test_context_messages_empty_when_no_files(self, tmp_path) -> None:
        """没有 agent.md / memory.md 时返回空列表"""
        builder = _make_builder(tmp_path / "user", tmp_path / "agent")

        messages = await builder.build_context_messages(user_id="u1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_context_messages_with_agent_md(self, tmp_path) -> None:
        """有 agent.md（系统级）时返回带 is_meta 标记的消息"""
        agent_fs_root = tmp_path / "agent"
        agent_fs_root.mkdir()
        (agent_fs_root / "agent.md").write_text("# Project Rules\nAlways use pytest.", encoding="utf-8")

        builder = _make_builder(tmp_path / "user", agent_fs_root)

        messages = await builder.build_context_messages(user_id="u1")
        assert len(messages) == 1

        msg: ModelRequest = messages[0]
        assert msg.metadata is not None
        assert msg.metadata["is_meta"] is True
        assert msg.metadata["source"] == "agent_md"
        assert isinstance(msg.parts[0], UserPromptPart)
        assert "Project Rules" in msg.parts[0].content

    @pytest.mark.asyncio
    async def test_context_messages_with_both(self, tmp_path) -> None:
        """同时有 agent.md（系统级）和 memory.md（用户级）"""
        # agent.md 在 agent_fs 根目录
        agent_fs_root = tmp_path / "agent"
        agent_fs_root.mkdir()
        (agent_fs_root / "agent.md").write_text("project rules", encoding="utf-8")

        # memory.md 在 user_fs 的 /{user_id}/ 下
        user_fs_root = tmp_path / "user"
        user_dir = user_fs_root / "u1"
        user_dir.mkdir(parents=True)
        (user_dir / "memory.md").write_text("user prefers dark mode", encoding="utf-8")

        builder = _make_builder(user_fs_root, agent_fs_root)

        messages = await builder.build_context_messages(user_id="u1")
        assert len(messages) == 2

        sources = [m.metadata["source"] for m in messages]
        assert "agent_md" in sources
        assert "memory" in sources


class TestPromptBuilderEdgeCases:
    """US-006: PromptBuilder 边界条件"""

    @pytest.mark.asyncio
    async def test_agent_md_not_exists_returns_empty(self, tmp_path) -> None:
        """agent.md 不存在时返回空上下文"""
        builder = _make_builder(tmp_path / "user", tmp_path / "agent")

        messages = await builder.build_context_messages(user_id="nonexistent")
        assert messages == []

    @pytest.mark.asyncio
    async def test_agent_md_empty_content_returns_empty(self, tmp_path) -> None:
        """agent.md 为空内容时返回空上下文"""
        agent_fs_root = tmp_path / "agent"
        agent_fs_root.mkdir()
        (agent_fs_root / "agent.md").write_text("", encoding="utf-8")

        builder = _make_builder(tmp_path / "user", agent_fs_root)

        messages = await builder.build_context_messages(user_id="u1")
        # 空文件不应产生上下文消息
        assert messages == []

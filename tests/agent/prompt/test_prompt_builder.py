"""PromptBuilder 测试"""

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from src.agent.prompt.prompt_builder import PromptBuilder
from src.storage.local_backend import FilesystemBackend


class TestPromptBuilder:

    def test_build_system_prompt(self, tmp_path) -> None:
        """系统提示词从模板加载"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        builder = PromptBuilder(backend)

        prompt = builder.build_system_prompt()
        assert "助手" in prompt
        assert len(prompt) > 10

    def test_build_system_prompt_cached(self, tmp_path) -> None:
        """系统提示词有缓存"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        builder = PromptBuilder(backend)

        p1 = builder.build_system_prompt()
        p2 = builder.build_system_prompt()
        assert p1 is p2  # 同一对象引用

    @pytest.mark.asyncio
    async def test_context_messages_empty_when_no_files(self, tmp_path) -> None:
        """没有 agent.md / memory.md 时返回空列表"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        builder = PromptBuilder(backend)

        messages = await builder.build_context_messages(user_id="u1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_context_messages_with_agent_md(self, tmp_path) -> None:
        """有 agent.md 时返回带 is_meta 标记的消息"""
        # 创建 data/{user_id}/agent.md
        user_dir = tmp_path / "u1"
        user_dir.mkdir()
        (user_dir / "agent.md").write_text("# Project Rules\nAlways use pytest.", encoding="utf-8")

        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        builder = PromptBuilder(backend)

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
        """同时有 agent.md 和 memory.md"""
        user_dir = tmp_path / "u1"
        user_dir.mkdir()
        (user_dir / "agent.md").write_text("project rules", encoding="utf-8")
        (user_dir / "memory.md").write_text("user prefers dark mode", encoding="utf-8")

        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        builder = PromptBuilder(backend)

        messages = await builder.build_context_messages(user_id="u1")
        assert len(messages) == 2

        sources = [m.metadata["source"] for m in messages]
        assert "agent_md" in sources
        assert "memory" in sources

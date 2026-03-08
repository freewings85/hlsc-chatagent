"""Agent.md API 端点测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.storage.local_backend import FilesystemBackend


class TestAgentMdApi:

    @pytest.fixture
    def client(self) -> TestClient:
        from src.server.app import app
        return TestClient(app)

    def test_get_agent_md_empty(self, client: TestClient, tmp_path: Path) -> None:
        """agent.md 不存在时返回空字符串"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with patch("src.server.agent_md_api.get_agent_fs_backend", return_value=backend):
            resp = client.get("/api/agent-md")
            assert resp.status_code == 200
            assert resp.json()["content"] == ""

    def test_get_agent_md_with_content(self, client: TestClient, tmp_path: Path) -> None:
        """agent.md 存在时返回内容"""
        (tmp_path / "agent.md").write_text("# Hello\nWorld", encoding="utf-8")
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with patch("src.server.agent_md_api.get_agent_fs_backend", return_value=backend):
            resp = client.get("/api/agent-md")
            assert resp.status_code == 200
            assert "Hello" in resp.json()["content"]

    def test_put_agent_md(self, client: TestClient, tmp_path: Path) -> None:
        """更新 agent.md"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with patch("src.server.agent_md_api.get_agent_fs_backend", return_value=backend):
            resp = client.put(
                "/api/agent-md",
                json={"content": "# New Content\nUpdated."},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            # 验证内容已写入
            resp2 = client.get("/api/agent-md")
            assert "New Content" in resp2.json()["content"]

    def test_put_agent_md_overwrites(self, client: TestClient, tmp_path: Path) -> None:
        """更新 agent.md 覆盖旧内容"""
        (tmp_path / "agent.md").write_text("old content", encoding="utf-8")
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with patch("src.server.agent_md_api.get_agent_fs_backend", return_value=backend):
            resp = client.put(
                "/api/agent-md",
                json={"content": "new content"},
            )
            assert resp.status_code == 200

            resp2 = client.get("/api/agent-md")
            assert resp2.json()["content"] == "new content"

    def test_put_empty_content(self, client: TestClient, tmp_path: Path) -> None:
        """写入空内容"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        with patch("src.server.agent_md_api.get_agent_fs_backend", return_value=backend):
            resp = client.put("/api/agent-md", json={"content": ""})
            assert resp.status_code == 200
            assert resp.json()["success"] is True

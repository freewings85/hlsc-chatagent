"""Prompt 管理 API 端点测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestPromptApi:

    @pytest.fixture
    def templates_dir(self, tmp_path: Path) -> Path:
        """创建临时 templates 目录"""
        d = tmp_path / "templates"
        d.mkdir()
        return d

    @pytest.fixture
    def client(self, templates_dir: Path) -> TestClient:
        with patch("src.agent.prompt.prompt_builder._TEMPLATES_DIR", templates_dir):
            from src.server.app import app
            yield TestClient(app)

    def test_list_empty(self, client: TestClient) -> None:
        """空目录返回空列表"""
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_list_with_files(self, client: TestClient, templates_dir: Path) -> None:
        """列出所有 .md 文件"""
        (templates_dir / "agent.md").write_text("# Agent", encoding="utf-8")
        (templates_dir / "identity.md").write_text("# Identity", encoding="utf-8")
        (templates_dir / "not-md.txt").write_text("ignored", encoding="utf-8")

        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        files = resp.json()["files"]
        names = {f["name"] for f in files}
        assert "agent.md" in names
        assert "identity.md" in names
        assert "not-md.txt" not in names

    def test_get_prompt(self, client: TestClient, templates_dir: Path) -> None:
        """读取指定文件内容"""
        (templates_dir / "agent.md").write_text("# Hello\nWorld", encoding="utf-8")

        resp = client.get("/api/prompts/agent.md")
        assert resp.status_code == 200
        assert "Hello" in resp.json()["content"]

    def test_get_prompt_not_found(self, client: TestClient) -> None:
        """文件不存在返回 404"""
        resp = client.get("/api/prompts/nonexistent.md")
        assert resp.status_code == 404

    def test_update_prompt(self, client: TestClient, templates_dir: Path) -> None:
        """更新文件内容"""
        (templates_dir / "agent.md").write_text("old", encoding="utf-8")

        resp = client.put("/api/prompts/agent.md", json={"content": "new content"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp2 = client.get("/api/prompts/agent.md")
        assert resp2.json()["content"] == "new content"

    def test_update_creates_new_file(self, client: TestClient, templates_dir: Path) -> None:
        """更新不存在的文件会创建"""
        resp = client.put(
            "/api/prompts/new-template.md",
            json={"content": "# New"},
        )
        assert resp.status_code == 200
        assert (templates_dir / "new-template.md").exists()

    def test_reject_non_md_extension(self, client: TestClient) -> None:
        """拒绝非 .md 文件"""
        resp = client.get("/api/prompts/evil.py")
        assert resp.status_code == 400

    def test_reject_path_traversal(self, client: TestClient) -> None:
        """拒绝路径穿越"""
        resp = client.get("/api/prompts/%2e%2e/%2e%2e/etc/passwd.md")
        assert resp.status_code == 400

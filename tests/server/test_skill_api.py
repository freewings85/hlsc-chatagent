"""Skill API 端点测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.skill_api import _resolve_skill_md_url
from src.storage.local_backend import FilesystemBackend


# --------------------------------------------------------------------------- #
# URL 解析测试
# --------------------------------------------------------------------------- #

class TestResolveSkillMdUrl:
    def test_github_tree_url(self) -> None:
        url = "https://github.com/anthropics/openclaw/tree/main/skills/github"
        result = _resolve_skill_md_url(url)
        assert result == "https://raw.githubusercontent.com/anthropics/openclaw/main/skills/github/SKILL.md"

    def test_github_tree_url_with_trailing_slash(self) -> None:
        url = "https://github.com/owner/repo/tree/main/skills/my-skill/"
        result = _resolve_skill_md_url(url)
        assert result == "https://raw.githubusercontent.com/owner/repo/main/skills/my-skill/SKILL.md"

    def test_github_tree_url_already_has_skill_md(self) -> None:
        url = "https://github.com/owner/repo/tree/main/skills/my-skill/SKILL.md"
        result = _resolve_skill_md_url(url)
        assert result == "https://raw.githubusercontent.com/owner/repo/main/skills/my-skill/SKILL.md"

    def test_github_blob_url(self) -> None:
        url = "https://github.com/owner/repo/blob/main/skills/my-skill/SKILL.md"
        result = _resolve_skill_md_url(url)
        assert result == "https://raw.githubusercontent.com/owner/repo/main/skills/my-skill/SKILL.md"

    def test_raw_url_passthrough(self) -> None:
        url = "https://raw.githubusercontent.com/owner/repo/main/skills/my-skill/SKILL.md"
        result = _resolve_skill_md_url(url)
        assert result == url

    def test_raw_url_directory_appends_skill_md(self) -> None:
        url = "https://raw.githubusercontent.com/owner/repo/main/skills/my-skill"
        result = _resolve_skill_md_url(url)
        assert result == url + "/SKILL.md"

    def test_generic_https_url(self) -> None:
        url = "https://example.com/my-skill/SKILL.md"
        result = _resolve_skill_md_url(url)
        assert result == url

    def test_invalid_source_raises(self) -> None:
        with pytest.raises(ValueError, match="不支持"):
            _resolve_skill_md_url("ftp://example.com/skill")

    def test_non_url_raises(self) -> None:
        with pytest.raises(ValueError, match="不支持"):
            _resolve_skill_md_url("just-a-name")

    def test_github_tree_deep_path(self) -> None:
        url = "https://github.com/user/repo/tree/feat/branch/a/b/c/skill"
        result = _resolve_skill_md_url(url)
        assert "raw.githubusercontent.com" in result
        assert result.endswith("/SKILL.md")


# --------------------------------------------------------------------------- #
# API 端点集成测试（使用 TestClient）
# --------------------------------------------------------------------------- #

class TestSkillApiEndpoints:

    @pytest.fixture
    def client(self) -> TestClient:
        from src.server.app import app
        return TestClient(app)

    def test_list_skills(self, client: TestClient) -> None:
        """GET /api/skills 返回列表"""
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # 至少有 bundled example skill
        names = [s["name"] for s in data]
        assert "example" in names

    def test_list_skills_structure(self, client: TestClient) -> None:
        """每个 skill 有必要字段"""
        resp = client.get("/api/skills")
        for skill in resp.json():
            assert "name" in skill
            assert "description" in skill
            assert "source" in skill

    def test_install_invalid_url(self, client: TestClient) -> None:
        """非法 URL 返回 400"""
        resp = client.post("/api/skills/install", json={"source": "not-a-url"})
        assert resp.status_code == 400

    def test_install_network_error(self, client: TestClient) -> None:
        """网络不可达返回 400"""
        resp = client.post(
            "/api/skills/install",
            json={"source": "https://nonexistent.invalid/SKILL.md"},
        )
        assert resp.status_code == 400

    def test_uninstall_nonexistent(self, client: TestClient) -> None:
        """卸载不存在的 skill 返回 404"""
        resp = client.delete("/api/skills/nonexistent_skill_xyz")
        assert resp.status_code == 404

    def test_install_and_uninstall_flow(self, client: TestClient, tmp_path: Path) -> None:
        """安装 → 验证 → 卸载 的完整流程（使用 mock HTTP + 真实 backend）。"""
        skill_content = (
            "---\nname: test-install\ndescription: Test skill for install\n---\n"
            "# Test Install\nDo things.\n"
        )

        skills_backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)

        with patch("src.server.skill_api.get_agent_fs_backend", return_value=skills_backend), \
             patch("src.server.skill_api.httpx.AsyncClient") as mock_client_cls:
            # Mock HTTP response
            mock_resp = AsyncMock()
            mock_resp.text = skill_content
            mock_resp.raise_for_status = lambda: None

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Install
            resp = client.post(
                "/api/skills/install",
                json={"source": "https://example.com/SKILL.md"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["skill"]["name"] == "test-install"

            # Verify file on disk via backend
            assert skills_backend.exists("/skills/test-install/SKILL.md")

            # Uninstall
            resp2 = client.delete("/api/skills/test-install")
            assert resp2.status_code == 200
            assert resp2.json()["success"] is True
            assert not skills_backend.exists("/skills/test-install")

    def test_install_invalid_skill_content(self, client: TestClient, tmp_path: Path) -> None:
        """下载到的内容不是有效 SKILL.md 时返回 400。"""
        skills_backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)

        with patch("src.server.skill_api.get_agent_fs_backend", return_value=skills_backend), \
             patch("src.server.skill_api.httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.text = "# Not a skill\nNo frontmatter here."
            mock_resp.raise_for_status = lambda: None

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = client.post(
                "/api/skills/install",
                json={"source": "https://example.com/SKILL.md"},
            )
            assert resp.status_code == 400
            assert "格式无效" in resp.json()["detail"]

"""skill ZIP 上传 API 测试"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def _patch_backend(tmp_path, monkeypatch):
    """用临时目录替换 agent_fs_backend"""
    from src.sdk._storage.local_backend import FilesystemBackend

    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
    monkeypatch.setattr(
        "src.sdk._server.skill_api.get_agent_fs_backend",
        lambda: backend,
    )
    return backend


@pytest.fixture()
def client(_patch_backend) -> TestClient:
    from src.sdk._server.app import app

    return TestClient(app)


def _make_zip(files: dict[str, str]) -> io.BytesIO:
    """创建内存 ZIP，files: {路径: 内容}"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


_VALID_SKILL_MD = """\
---
name: test-skill
description: A test skill
---

# Test Skill

This is a test.
"""


class TestUploadSkill:
    def test_upload_with_subdirectory(self, client: TestClient) -> None:
        """ZIP 内有外层目录：test-skill/SKILL.md"""
        buf = _make_zip({
            "test-skill/SKILL.md": _VALID_SKILL_MD,
            "test-skill/scripts/run.py": "print('hello')",
            "test-skill/references/api.md": "# API docs",
        })
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("test-skill.zip", buf, "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill"]["name"] == "test-skill"
        assert "3 个文件" in data["message"]

    def test_upload_flat_structure(self, client: TestClient) -> None:
        """ZIP 根目录直接放 SKILL.md"""
        buf = _make_zip({
            "SKILL.md": _VALID_SKILL_MD,
            "scripts/run.sh": "echo hello",
        })
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("skill.zip", buf, "application/zip")},
        )
        assert resp.status_code == 200
        assert resp.json()["skill"]["name"] == "test-skill"

    def test_upload_no_skill_md(self, client: TestClient) -> None:
        """ZIP 内没有 SKILL.md → 400"""
        buf = _make_zip({"scripts/run.py": "print('hello')"})
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("bad.zip", buf, "application/zip")},
        )
        assert resp.status_code == 400
        assert "SKILL.md" in resp.json()["detail"]

    def test_upload_invalid_skill_md(self, client: TestClient) -> None:
        """SKILL.md 格式错误 → 400"""
        buf = _make_zip({"SKILL.md": "no frontmatter here"})
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("bad.zip", buf, "application/zip")},
        )
        assert resp.status_code == 400
        assert "格式无效" in resp.json()["detail"]

    def test_upload_path_traversal(self, client: TestClient) -> None:
        """路径穿越 → 400"""
        buf = _make_zip({"../etc/passwd": "root:x:0:0"})
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("evil.zip", buf, "application/zip")},
        )
        assert resp.status_code == 400
        assert "不安全" in resp.json()["detail"]

    def test_upload_disallowed_extension(self, client: TestClient) -> None:
        """不允许的文件类型 → 400"""
        buf = _make_zip({
            "SKILL.md": _VALID_SKILL_MD,
            "scripts/payload.exe": "MZ...",
        })
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("bad.zip", buf, "application/zip")},
        )
        assert resp.status_code == 400
        assert ".exe" in resp.json()["detail"]

    def test_upload_not_zip(self, client: TestClient) -> None:
        """非 ZIP 文件 → 400"""
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("test.txt", io.BytesIO(b"not a zip"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_overwrites_existing(self, client: TestClient, _patch_backend) -> None:
        """上传同名 skill 覆盖旧版本"""
        buf1 = _make_zip({"SKILL.md": _VALID_SKILL_MD})
        client.post("/api/skills/upload", files={"file": ("v1.zip", buf1, "application/zip")})

        updated_md = _VALID_SKILL_MD.replace("A test skill", "Updated description")
        buf2 = _make_zip({
            "SKILL.md": updated_md,
            "scripts/new.py": "print('new')",
        })
        resp = client.post("/api/skills/upload", files={"file": ("v2.zip", buf2, "application/zip")})
        assert resp.status_code == 200
        assert resp.json()["skill"]["description"] == "Updated description"

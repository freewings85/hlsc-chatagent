"""Playwright 测试：Skill ZIP 上传 UI 功能验证。

启动真实服务器 + vite preview，从前端视角验证上传流程。
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

# 端口（用不同端口避免与 conftest 的 session-scoped server 冲突）
BACKEND_PORT = 8198
FRONTEND_PORT = 4174

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def _make_skill_zip(tmp_dir: Path, name: str = "demo-skill") -> Path:
    """在 tmp_dir 创建一个合法的 skill zip 文件"""
    zip_path = tmp_dir / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{name}/SKILL.md", f"""\
---
name: {name}
description: 这是一个演示 skill，用于测试上传功能
---

# {name}

这是一个测试用的 skill。

## 使用方式

通过 bash 执行脚本：

```bash
python {{{{baseDir}}}}/scripts/run.py
```
""")
        zf.writestr(f"{name}/scripts/run.py", """\
#!/usr/bin/env python3
print("Hello from demo skill!")
""")
        zf.writestr(f"{name}/references/guide.md", """\
# 使用指南

这是参考文档。
""")
    return zip_path


def _make_bad_zip(tmp_dir: Path) -> Path:
    """创建一个缺少 SKILL.md 的无效 zip"""
    zip_path = tmp_dir / "bad-skill.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("scripts/run.py", "print('no skill.md')")
    return zip_path


@pytest.fixture(scope="module")
def servers():
    """启动后端 + vite preview"""
    test_data = PROJECT_ROOT / "data" / "playwright_skill_upload"
    test_data.mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "SERVER_PORT": str(BACKEND_PORT),
        "DATA_DIR": str(test_data),
    }

    # 启动后端
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agent_sdk._server.app:app",
         "--host", "127.0.0.1",
         "--port", str(BACKEND_PORT),
         "--log-level", "info"],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Build 前端（注入后端地址）并启动 vite preview
    subprocess.run(
        ["npx", "vite", "build"],
        cwd=str(WEB_DIR),
        env={**os.environ, "VITE_API_BASE": f"http://127.0.0.1:{BACKEND_PORT}"},
        check=True,
        capture_output=True,
    )
    frontend = subprocess.Popen(
        ["npx", "vite", "preview", "--port", str(FRONTEND_PORT), "--strictPort"],
        cwd=str(WEB_DIR),
    )

    # 等待后端就绪（清除 proxy 避免干扰 localhost 请求）
    backend_url = f"http://127.0.0.1:{BACKEND_PORT}"
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(v, None)
    for _ in range(30):
        try:
            r = httpx.get(f"{backend_url}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        # 打印后端启动日志便于调试
        backend.terminate()
        try:
            out, _ = backend.communicate(timeout=3)
            print(f"Backend stdout:\n{out.decode(errors='replace')}")
        except Exception:
            pass
        frontend.terminate()
        pytest.fail("Backend failed to start")

    # 等待前端就绪
    frontend_url = f"http://127.0.0.1:{FRONTEND_PORT}"
    for _ in range(15):
        try:
            r = httpx.get(frontend_url, timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        backend.terminate()
        frontend.terminate()
        pytest.fail("Frontend failed to start")

    yield {"backend": backend_url, "frontend": frontend_url}

    backend.terminate()
    frontend.terminate()
    try:
        backend.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend.kill()
    try:
        frontend.wait(timeout=5)
    except subprocess.TimeoutExpired:
        frontend.kill()

    # 清理测试数据
    import shutil
    if test_data.exists():
        shutil.rmtree(test_data, ignore_errors=True)


@pytest.fixture()
def settings_page(page: Page, servers: dict) -> Page:
    """导航到 Settings > Skills 页面"""
    page.goto(f"{servers['frontend']}/settings/skills")
    page.wait_for_selector(".install-section", timeout=10_000)
    return page


@pytest.fixture()
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


SCREENSHOT_DIR = PROJECT_ROOT / "tests" / "e2e" / "screenshots"


def _screenshot(page: Page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"), full_page=True)


class TestSkillUploadUI:
    def test_page_shows_upload_button(self, settings_page: Page) -> None:
        """页面包含"上传 ZIP"按钮"""
        upload_btn = settings_page.locator("button:text('上传 ZIP')")
        expect(upload_btn).to_be_visible()
        _screenshot(settings_page, "01_skills_page_initial")

    def test_page_shows_directory_structure(self, settings_page: Page) -> None:
        """帮助区域展示 ZIP 目录结构"""
        help_tree = settings_page.locator(".help-tree")
        expect(help_tree).to_be_visible()
        expect(help_tree).to_contain_text("SKILL.md")
        expect(help_tree).to_contain_text("scripts/")
        expect(help_tree).to_contain_text("references/")
        _screenshot(settings_page, "02_directory_structure_help")

    def test_upload_valid_zip(self, settings_page: Page, tmp_dir: Path) -> None:
        """上传合法 ZIP → 成功安装，列表中出现新 skill"""
        zip_path = _make_skill_zip(tmp_dir)

        # 通过 file chooser 上传
        with settings_page.expect_file_chooser() as fc_info:
            settings_page.locator("button:text('上传 ZIP')").click()
        file_chooser = fc_info.value
        file_chooser.set_files(str(zip_path))

        # 等待成功消息
        success_msg = settings_page.locator(".msg.success")
        expect(success_msg).to_be_visible(timeout=10_000)
        expect(success_msg).to_contain_text("demo-skill")

        # skill 列表中应出现新 skill
        skill_card = settings_page.locator(".skill-name:text('demo-skill')")
        expect(skill_card).to_be_visible()

        _screenshot(settings_page, "03_upload_success")

    def test_upload_invalid_zip(self, settings_page: Page, tmp_dir: Path) -> None:
        """上传缺少 SKILL.md 的 ZIP → 错误消息"""
        zip_path = _make_bad_zip(tmp_dir)

        with settings_page.expect_file_chooser() as fc_info:
            settings_page.locator("button:text('上传 ZIP')").click()
        file_chooser = fc_info.value
        file_chooser.set_files(str(zip_path))

        # 等待错误消息
        error_msg = settings_page.locator(".msg.error")
        expect(error_msg).to_be_visible(timeout=10_000)
        expect(error_msg).to_contain_text("SKILL.md")

        _screenshot(settings_page, "04_upload_error")

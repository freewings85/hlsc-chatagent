"""Skill 管理 API：安装 / 卸载 / 列表。

支持的安装源：
  1. GitHub 目录 URL：https://github.com/{owner}/{repo}/tree/{branch}/skills/{name}
  2. GitHub 原始文件 URL：https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{name}/SKILL.md
  3. 任意 HTTPS URL（直接指向 SKILL.md 文件）
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agent.skills.registry import SkillRegistry, get_default_skill_dirs, parse_skill_file

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/skills", tags=["skills"])

# 安装目标目录：项目级（.chatagent/skills/）
_INSTALL_DIR: Path = Path(".chatagent") / "skills"

# GitHub tree URL → raw URL 转换
# https://github.com/{owner}/{repo}/tree/{branch}/{path}
_GITHUB_TREE_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"/tree/(?P<branch>[^/]+)/(?P<path>.+)"
)

# GitHub blob URL
# https://github.com/{owner}/{repo}/blob/{branch}/{path}
_GITHUB_BLOB_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"/blob/(?P<branch>[^/]+)/(?P<path>.+)"
)

# raw.githubusercontent.com URL（已经是直接文件）
_GITHUB_RAW_RE = re.compile(
    r"https?://raw\.githubusercontent\.com/"
)


# --------------------------------------------------------------------------- #
# Request / Response Models
# --------------------------------------------------------------------------- #

class InstallRequest(BaseModel):
    source: str
    """安装源：GitHub URL 或直接 SKILL.md URL"""


class SkillInfo(BaseModel):
    name: str
    description: str
    source: str  # "bundled" | "project" | "user"
    when_to_use: str | None = None
    user_invocable: bool = True


class InstallResponse(BaseModel):
    success: bool
    skill: SkillInfo | None = None
    message: str = ""


# --------------------------------------------------------------------------- #
# URL → raw SKILL.md URL 解析
# --------------------------------------------------------------------------- #

def _resolve_skill_md_url(source: str) -> str:
    """将各种 GitHub URL 格式统一转为可下载的 SKILL.md raw URL。"""
    source = source.strip()

    # 已经是 raw URL
    if _GITHUB_RAW_RE.match(source):
        if not source.endswith("SKILL.md"):
            # 可能是目录路径，追加 SKILL.md
            source = source.rstrip("/") + "/SKILL.md"
        return source

    # GitHub tree URL（目录）
    m = _GITHUB_TREE_RE.match(source)
    if m:
        owner, repo, branch, path = m.group("owner"), m.group("repo"), m.group("branch"), m.group("path")
        path = path.rstrip("/")
        if not path.endswith("SKILL.md"):
            path = f"{path}/SKILL.md"
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

    # GitHub blob URL（文件）
    m = _GITHUB_BLOB_RE.match(source)
    if m:
        owner, repo, branch, path = m.group("owner"), m.group("repo"), m.group("branch"), m.group("path")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

    # 其他 HTTPS URL，假设直接指向 SKILL.md
    if source.startswith("http://") or source.startswith("https://"):
        return source

    raise ValueError(f"不支持的安装源格式: {source}")


def _classify_source(skill_path: Path) -> str:
    """判断 skill 来源：bundled / project / user。"""
    try:
        rel = skill_path.resolve()
        bundled_dir = (Path(__file__).parent.parent / "agent" / "skills" / "bundled").resolve()
        project_dir = _INSTALL_DIR.resolve()
        user_dir = (Path.home() / ".chatagent" / "skills").resolve()

        if str(rel).startswith(str(bundled_dir)):
            return "bundled"
        if str(rel).startswith(str(project_dir)):
            return "project"
        if str(rel).startswith(str(user_dir)):
            return "user"
    except Exception:
        pass
    return "unknown"


# --------------------------------------------------------------------------- #
# API Endpoints
# --------------------------------------------------------------------------- #

@router.get("")
async def list_skills() -> list[SkillInfo]:
    """列出所有已加载的 skills。"""
    registry = SkillRegistry.load(get_default_skill_dirs())
    result: list[SkillInfo] = []
    for entry in sorted(registry._entries.values(), key=lambda e: e.name):
        source = _classify_source(entry.source_path) if entry.source_path else "unknown"
        result.append(SkillInfo(
            name=entry.name,
            description=entry.description,
            source=source,
            when_to_use=entry.when_to_use,
            user_invocable=entry.user_invocable,
        ))
    return result


@router.post("/install")
async def install_skill(req: InstallRequest) -> InstallResponse:
    """从 URL 安装 skill。

    下载 SKILL.md → 解析验证 → 存入 .chatagent/skills/{name}/SKILL.md。
    """
    # 1. 解析 URL
    try:
        raw_url = _resolve_skill_md_url(req.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 下载
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(raw_url)
            resp.raise_for_status()
            content = resp.text
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400,
            detail=f"下载失败 (HTTP {e.response.status_code}): {raw_url}",
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"网络错误: {e}")

    # 3. 写入临时文件 → 解析验证
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = _INSTALL_DIR / "_tmp_install_skill.md"
    try:
        tmp_file.write_text(content, encoding="utf-8")
        entry = parse_skill_file(tmp_file)
        if entry is None:
            raise HTTPException(
                status_code=400,
                detail="SKILL.md 格式无效：缺少 name 或 description 字段，或无 YAML frontmatter",
            )
    finally:
        tmp_file.unlink(missing_ok=True)

    # 4. 安装到 .chatagent/skills/{name}/SKILL.md
    skill_dir = _INSTALL_DIR / entry.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")

    logger.info("Skill installed: %s → %s", entry.name, skill_file)

    return InstallResponse(
        success=True,
        skill=SkillInfo(
            name=entry.name,
            description=entry.description,
            source="project",
            when_to_use=entry.when_to_use,
            user_invocable=entry.user_invocable,
        ),
        message=f"已安装 skill: {entry.name}",
    )


@router.delete("/{name}")
async def uninstall_skill(name: str) -> InstallResponse:
    """卸载 project 级 skill（不允许卸载 bundled）。"""
    skill_dir = _INSTALL_DIR / name
    if not skill_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未安装（project 级）")

    # 确认是 project 级
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 目录不含 SKILL.md")

    shutil.rmtree(skill_dir)
    logger.info("Skill uninstalled: %s", name)

    return InstallResponse(
        success=True,
        message=f"已卸载 skill: {name}",
    )

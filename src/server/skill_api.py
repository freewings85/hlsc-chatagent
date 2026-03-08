"""Skill 管理 API：安装 / 卸载 / 列表。

支持的安装源：
  1. GitHub 目录 URL：https://github.com/{owner}/{repo}/tree/{branch}/skills/{name}
  2. GitHub 原始文件 URL：https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{name}/SKILL.md
  3. 任意 HTTPS URL（直接指向 SKILL.md 文件）

安装/卸载通过 Agent 文件资源 backend（root=AGENT_FS_DIR）操作，
与用户数据 backend（root=USER_FS_DIR）隔离，集群部署时所有节点共享。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agent.skills.registry import SkillRegistry, get_default_skill_dirs, parse_skill_content
from src.config.settings import get_agent_fs_backend

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/skills", tags=["skills"])

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
    source: str  # "bundled" | "project"
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
    """判断 skill 来源：bundled / project。"""
    try:
        rel = skill_path.resolve()
        bundled_dir = (Path(__file__).parent.parent / "agent" / "skills" / "bundled").resolve()

        if str(rel).startswith(str(bundled_dir)):
            return "bundled"
    except Exception:
        pass
    # 非 bundled 的都是 project 级
    return "project"


# --------------------------------------------------------------------------- #
# API Endpoints
# --------------------------------------------------------------------------- #

@router.get("")
async def list_skills() -> list[SkillInfo]:
    """列出所有已加载的 skills。"""
    registry = SkillRegistry.load(get_default_skill_dirs())
    result: list[SkillInfo] = []
    for entry in sorted(registry._entries.values(), key=lambda e: e.name):
        source = _classify_source(entry.source_path) if entry.source_path else "project"
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

    下载 SKILL.md → 解析验证 → 通过 skills backend 写入 {name}/SKILL.md。
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

    # 3. 直接解析内容验证（无需临时文件）
    entry = parse_skill_content(content)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail="SKILL.md 格式无效：缺少 name 或 description 字段，或无 YAML frontmatter",
        )

    # 4. 通过 agent_fs backend 写入 skills/{name}/SKILL.md
    backend = get_agent_fs_backend()
    skill_path = f"/skills/{entry.name}/SKILL.md"

    # 先删除旧版本（如果存在），再写入新内容
    if await backend.aexists(f"/skills/{entry.name}"):
        await backend.adelete(f"/skills/{entry.name}")

    upload_results = await backend.aupload_files(
        [(skill_path, content.encode("utf-8"))]
    )
    if upload_results[0].error:
        raise HTTPException(
            status_code=500,
            detail=f"写入 skill 文件失败: {upload_results[0].error}",
        )

    logger.info("Skill installed: %s → %s", entry.name, skill_path)

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
    backend = get_agent_fs_backend()
    skill_dir = f"/skills/{name}"
    skill_file = f"/skills/{name}/SKILL.md"

    if not await backend.aexists(skill_dir):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未安装（project 级）")

    if not await backend.aexists(skill_file):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 目录不含 SKILL.md")

    deleted = await backend.adelete(skill_dir)
    if not deleted:
        raise HTTPException(status_code=500, detail=f"删除 skill '{name}' 失败")

    logger.info("Skill uninstalled: %s", name)

    return InstallResponse(
        success=True,
        message=f"已卸载 skill: {name}",
    )

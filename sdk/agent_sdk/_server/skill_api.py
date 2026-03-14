"""Skill 管理 API：安装 / 卸载 / 列表 / 上传。

支持的安装源：
  1. GitHub 目录 URL：https://github.com/{owner}/{repo}/tree/{branch}/skills/{name}
  2. GitHub 原始文件 URL：https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{name}/SKILL.md
  3. 任意 HTTPS URL（直接指向 SKILL.md 文件）
  4. ZIP 压缩包上传（包含完整 skill 目录结构）

安装/卸载通过 Agent 文件资源 backend（root=AGENT_FS_DIR）操作，
与用户数据 backend（root=DATA_DIR）隔离，集群部署时所有节点共享。
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path, PurePosixPath

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from agent_sdk._agent.skills.registry import SkillRegistry, get_default_skill_dirs, parse_skill_content
from agent_sdk._config.settings import get_agent_fs_backend

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
        bundled_dir = (Path(__file__).parent.parent / "_agent" / "skills" / "bundled").resolve()

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


# 上传限制
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_FILES_IN_ZIP = 50
# 允许的文件后缀（安全白名单）
_ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".py", ".sh", ".bash", ".js", ".ts",
    ".json", ".yaml", ".yml", ".toml", ".env", ".cfg", ".ini",
    ".html", ".css",
}


def _is_safe_zip_entry(name: str) -> bool:
    """检查 zip 内文件路径是否安全（防路径穿越）。"""
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return False
    return True


@router.post("/upload")
async def upload_skill(file: UploadFile) -> InstallResponse:
    """上传 ZIP 压缩包安装 skill。

    ZIP 结构要求：
      skill-name/
      ├── SKILL.md          # 必须，skill 定义文件
      ├── scripts/           # 可选，可执行脚本
      ├── references/        # 可选，参考文档
      └── ...

    或者 ZIP 根目录直接包含 SKILL.md（无外层目录）。
    """
    if file.content_type not in ("application/zip", "application/x-zip-compressed"):
        # 有些浏览器会发 application/octet-stream，也接受 .zip 后缀
        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(
                status_code=400,
                detail="请上传 .zip 格式的压缩包",
            )

    # 1. 读取并校验大小
    data = await file.read()
    if len(data) > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大（{len(data) // 1024 // 1024}MB），最大 {_MAX_UPLOAD_SIZE // 1024 // 1024}MB",
        )

    # 2. 解析 ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="无效的 ZIP 文件")

    entries = [e for e in zf.namelist() if not e.endswith("/")]
    if len(entries) > _MAX_FILES_IN_ZIP:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP 内文件过多（{len(entries)} 个），最多 {_MAX_FILES_IN_ZIP} 个",
        )

    # 3. 安全检查
    for name in entries:
        if not _is_safe_zip_entry(name):
            raise HTTPException(
                status_code=400,
                detail=f"ZIP 内包含不安全的路径: {name}",
            )

    # 4. 定位 SKILL.md — 支持两种结构
    #    a) skill-name/SKILL.md（有外层目录）
    #    b) SKILL.md（根目录直接放）
    skill_md_path: str | None = None
    strip_prefix: str = ""

    for name in entries:
        parts = PurePosixPath(name).parts
        if parts[-1] == "SKILL.md":
            if len(parts) == 1:
                # 根目录直接放 SKILL.md
                skill_md_path = name
                strip_prefix = ""
                break
            elif len(parts) == 2:
                # skill-name/SKILL.md
                skill_md_path = name
                strip_prefix = parts[0] + "/"
                break

    if skill_md_path is None:
        raise HTTPException(
            status_code=400,
            detail="ZIP 内未找到 SKILL.md（应在根目录或第一层子目录下）",
        )

    # 5. 解析 SKILL.md 验证格式
    skill_md_content = zf.read(skill_md_path).decode("utf-8")
    entry = parse_skill_content(skill_md_content)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail="SKILL.md 格式无效：缺少 name 或 description 字段，或无 YAML frontmatter",
        )

    # 6. 检查文件后缀白名单
    for name in entries:
        relative = name[len(strip_prefix):] if strip_prefix else name
        suffix = PurePosixPath(relative).suffix.lower()
        # 无后缀的文件（如 Makefile）允许通过
        if suffix and suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不允许的文件类型 '{suffix}': {relative}（允许: {', '.join(sorted(_ALLOWED_EXTENSIONS))}）",
            )

    # 7. 写入 backend
    backend = get_agent_fs_backend()
    skill_dir = f"/skills/{entry.name}"

    # 先删除旧版本
    if await backend.aexists(skill_dir):
        await backend.adelete(skill_dir)

    # 逐文件写入
    write_count = 0
    for name in entries:
        relative = name[len(strip_prefix):] if strip_prefix else name
        if not relative:
            continue
        dest_path = f"/skills/{entry.name}/{relative}"
        content = zf.read(name)
        results = await backend.aupload_files([(dest_path, content)])
        if results[0].error:
            raise HTTPException(
                status_code=500,
                detail=f"写入文件失败: {dest_path}: {results[0].error}",
            )
        write_count += 1

    logger.info("Skill uploaded: %s (%d files)", entry.name, write_count)

    return InstallResponse(
        success=True,
        skill=SkillInfo(
            name=entry.name,
            description=entry.description,
            source="project",
            when_to_use=entry.when_to_use,
            user_invocable=entry.user_invocable,
        ),
        message=f"已安装 skill: {entry.name}（{write_count} 个文件）",
    )

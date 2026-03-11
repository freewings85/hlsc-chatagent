"""Prompt 管理 API：列出、查看、编辑 prompts/templates/ 下的提示词文件。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import src.agent.prompt.prompt_builder as _pb

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/prompts", tags=["prompts"])

# 允许编辑的文件后缀白名单
_ALLOWED_EXTENSIONS: set[str] = {".md"}


class PromptFileInfo(BaseModel):
    """单个提示词文件信息。"""
    name: str
    path: str
    size: int


class PromptListResponse(BaseModel):
    files: list[PromptFileInfo]


class PromptContentResponse(BaseModel):
    path: str
    content: str


class PromptUpdateRequest(BaseModel):
    content: str


class PromptUpdateResponse(BaseModel):
    success: bool
    message: str = ""


def _resolve_and_validate(file_path: str) -> Path:
    """解析路径并校验安全性（防止路径穿越）。"""
    resolved = (_pb._TEMPLATES_DIR / file_path).resolve()
    templates_resolved = _pb._TEMPLATES_DIR.resolve()
    if not str(resolved).startswith(str(templates_resolved)):
        raise HTTPException(status_code=400, detail="路径不合法")
    if resolved.suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {resolved.suffix}")
    return resolved


@router.get("", response_model=PromptListResponse)
async def list_prompts() -> PromptListResponse:
    """列出所有提示词文件。"""
    files: list[PromptFileInfo] = []
    templates_resolved = _pb._TEMPLATES_DIR.resolve()

    if not _pb._TEMPLATES_DIR.exists():
        return PromptListResponse(files=[])

    for p in sorted(_pb._TEMPLATES_DIR.rglob("*")):
        if not p.is_file() or p.suffix not in _ALLOWED_EXTENSIONS:
            continue
        rel = str(p.resolve().relative_to(templates_resolved))
        files.append(PromptFileInfo(
            name=p.name,
            path=rel,
            size=p.stat().st_size,
        ))

    return PromptListResponse(files=files)


@router.get("/{file_path:path}", response_model=PromptContentResponse)
async def get_prompt(file_path: str) -> PromptContentResponse:
    """读取指定提示词文件内容。"""
    resolved = _resolve_and_validate(file_path)

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=500, detail="文件编码错误")

    return PromptContentResponse(path=file_path, content=content)


@router.put("/{file_path:path}", response_model=PromptUpdateResponse)
async def update_prompt(file_path: str, req: PromptUpdateRequest) -> PromptUpdateResponse:
    """更新指定提示词文件内容（全量替换）。"""
    resolved = _resolve_and_validate(file_path)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(req.content, encoding="utf-8")

    logger.info("Prompt updated: %s (%d chars)", file_path, len(req.content))

    return PromptUpdateResponse(
        success=True,
        message=f"{file_path} 已更新",
    )

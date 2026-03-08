"""Agent.md 管理 API：查看 / 编辑系统级 agent.md。

agent.md 存储在 AGENT_FS_DIR 根目录，通过 agent_fs backend 读写，
集群部署时所有节点共享。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config.settings import get_agent_fs_backend

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/agent-md", tags=["agent-md"])

_AGENT_MD_PATH = "/agent.md"


class AgentMdResponse(BaseModel):
    content: str


class AgentMdUpdateRequest(BaseModel):
    content: str


class AgentMdUpdateResponse(BaseModel):
    success: bool
    message: str = ""


@router.get("")
async def get_agent_md() -> AgentMdResponse:
    """读取 agent.md 内容。"""
    backend = get_agent_fs_backend()

    if not await backend.aexists(_AGENT_MD_PATH):
        return AgentMdResponse(content="")

    results = await backend.adownload_files([_AGENT_MD_PATH])
    if results[0].error or results[0].content is None:
        return AgentMdResponse(content="")

    try:
        content = results[0].content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=500, detail="agent.md 编码错误")

    return AgentMdResponse(content=content)


@router.put("")
async def update_agent_md(req: AgentMdUpdateRequest) -> AgentMdUpdateResponse:
    """更新 agent.md 内容（全量替换）。"""
    backend = get_agent_fs_backend()

    # 先删除旧文件（如果存在），再写入
    if await backend.aexists(_AGENT_MD_PATH):
        await backend.adelete(_AGENT_MD_PATH)

    upload_results = await backend.aupload_files(
        [(_AGENT_MD_PATH, req.content.encode("utf-8"))]
    )
    if upload_results[0].error:
        raise HTTPException(
            status_code=500,
            detail=f"写入 agent.md 失败: {upload_results[0].error}",
        )

    logger.info("agent.md updated (%d chars)", len(req.content))

    return AgentMdUpdateResponse(
        success=True,
        message="agent.md 已更新",
    )

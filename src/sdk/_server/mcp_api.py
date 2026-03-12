"""MCP 管理 API：添加 / 移除 / 列表 / 探测 MCP 服务器。

配置存储在 {AGENT_FS_DIR}/mcp.json，通过 agent_fs_backend 读写。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.sdk._agent.mcp.config import (
    McpConfig,
    McpServerEntry,
    load_mcp_config,
    save_mcp_config,
)
from src.sdk._config.settings import get_agent_fs_backend

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/mcp", tags=["mcp"])


# --------------------------------------------------------------------------- #
# Request / Response Models
# --------------------------------------------------------------------------- #


class McpServerInfo(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = {}


class AddServerRequest(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = {}


class McpToolInfo(BaseModel):
    name: str
    description: str | None = None


class ProbeResponse(BaseModel):
    success: bool
    tools: list[McpToolInfo] = []
    error: str = ""


class McpResponse(BaseModel):
    success: bool
    message: str = ""


# --------------------------------------------------------------------------- #
# API Endpoints
# --------------------------------------------------------------------------- #


@router.get("/servers")
async def list_servers() -> list[McpServerInfo]:
    """列出所有已配置的 MCP 服务器。"""
    backend = get_agent_fs_backend()
    config = await load_mcp_config(backend)
    return [
        McpServerInfo(name=name, url=entry.url, headers=entry.headers)
        for name, entry in config.servers.items()
    ]


@router.post("/servers")
async def add_server(req: AddServerRequest) -> McpResponse:
    """添加或更新 MCP 服务器配置。"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="服务器名称不能为空")
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL 不能为空")

    backend = get_agent_fs_backend()
    config = await load_mcp_config(backend)

    is_update = req.name in config.servers
    config.servers[req.name] = McpServerEntry(
        name=req.name,
        url=req.url.strip(),
        headers=req.headers,
    )

    await save_mcp_config(backend, config)
    action = "更新" if is_update else "添加"
    logger.info("MCP server %s: %s → %s", action, req.name, req.url)

    return McpResponse(success=True, message=f"已{action} MCP 服务器: {req.name}")


@router.delete("/servers/{name}")
async def remove_server(name: str) -> McpResponse:
    """移除 MCP 服务器配置。"""
    backend = get_agent_fs_backend()
    config = await load_mcp_config(backend)

    if name not in config.servers:
        raise HTTPException(status_code=404, detail=f"MCP 服务器 '{name}' 未配置")

    del config.servers[name]
    await save_mcp_config(backend, config)
    logger.info("MCP server removed: %s", name)

    return McpResponse(success=True, message=f"已移除 MCP 服务器: {name}")


@router.post("/servers/{name}/probe")
async def probe_server(name: str) -> ProbeResponse:
    """探测 MCP 服务器，获取可用工具列表。"""
    backend = get_agent_fs_backend()
    config = await load_mcp_config(backend)

    entry = config.servers.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务器 '{name}' 未配置")

    try:
        from fastmcp.client import Client

        async with Client(transport=entry.url) as client:
            tools = await client.list_tools()
            return ProbeResponse(
                success=True,
                tools=[
                    McpToolInfo(
                        name=t.name,
                        description=t.description,
                    )
                    for t in tools
                ],
            )
    except Exception as e:
        logger.warning("探测 MCP 服务器 '%s' 失败: %s", name, e)
        return ProbeResponse(success=False, error=str(e))


@router.post("/probe-url")
async def probe_url(req: AddServerRequest) -> ProbeResponse:
    """探测指定 URL 的 MCP 服务器（无需先保存配置）。"""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL 不能为空")

    try:
        from fastmcp.client import Client

        async with Client(transport=req.url.strip()) as client:
            tools = await client.list_tools()
            return ProbeResponse(
                success=True,
                tools=[
                    McpToolInfo(
                        name=t.name,
                        description=t.description,
                    )
                    for t in tools
                ],
            )
    except Exception as e:
        logger.warning("探测 URL '%s' 失败: %s", req.url, e)
        return ProbeResponse(success=False, error=str(e))

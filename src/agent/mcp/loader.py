"""MCP Toolset 加载器：从 McpConfig 创建 FastMCPToolset 实例。

每次 agent loop 调用 load_mcp_toolsets() 获取最新的 MCP toolsets，
传给 agent.iter(toolsets=[...])，实现动态 MCP 配置。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai.toolsets import AbstractToolset

from src.agent.mcp.config import McpConfig, load_mcp_config
from src.common.filesystem_backend import BackendProtocol

logger: logging.Logger = logging.getLogger(__name__)


async def load_mcp_toolsets(
    backend: BackendProtocol,
) -> list[AbstractToolset[Any]]:
    """从 agent_fs backend 加载 MCP 配置，返回 FastMCPToolset 列表。

    每个配置的 MCP 服务器创建一个 FastMCPToolset（HTTP transport）。
    加载失败的服务器会记录警告并跳过（不影响其他服务器）。
    """
    config = await load_mcp_config(backend)
    if not config.servers:
        return []

    from pydantic_ai.toolsets.fastmcp import FastMCPToolset

    toolsets: list[AbstractToolset[Any]] = []
    for name, entry in config.servers.items():
        try:
            toolset = FastMCPToolset(
                entry.url,
                id=name,
            )
            toolsets.append(toolset)
            logger.info("MCP toolset loaded: %s → %s", name, entry.url)
        except Exception as e:
            logger.warning("MCP toolset '%s' 创建失败: %s", name, e)

    return toolsets

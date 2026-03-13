"""MCP Toolset 加载器：从 McpConfig 创建 FastMCPToolset 实例。

每次 agent loop 调用 load_mcp_toolsets() 获取最新的 MCP toolsets，
传给 agent.iter(toolsets=[...])，实现动态 MCP 配置。
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

from pydantic_ai.toolsets import AbstractToolset

from agent_sdk._agent.mcp.config import load_mcp_config
from agent_sdk._common.filesystem_backend import BackendProtocol

logger: logging.Logger = logging.getLogger(__name__)


class _PreconnectedToolset(AbstractToolset[Any]):
    """包装已通过预连接验证的 FastMCPToolset。

    agent.iter() 会对 toolsets 调 __aenter__，这个 wrapper 避免重复连接：
    - __aenter__：直接返回（已连接）
    - __aexit__：委托给原始 toolset 关闭连接
    - 其余方法全部委托给原始 toolset
    """

    def __init__(self, inner: AbstractToolset[Any]) -> None:
        self._inner = inner

    async def __aenter__(self) -> _PreconnectedToolset:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._inner.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def id(self) -> str:
        return self._inner.id

    def get_tools(self, ctx: Any) -> Any:
        return self._inner.get_tools(ctx)

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: Any, tool: Any) -> Any:
        return await self._inner.call_tool(name, tool_args, ctx, tool)


async def load_mcp_toolsets(
    backend: BackendProtocol,
) -> list[AbstractToolset[Any]]:
    """从 agent_fs backend 加载 MCP 配置，返回已验证连接的 toolset 列表。

    对每个配置的 MCP 服务器执行预连接验证（__aenter__）：
    - 连接成功：保持连接，包装为 _PreconnectedToolset 返回
    - 连接失败：记录警告并跳过，不影响其他服务器
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
            # 预连接验证：实际建立 MCP 连接
            await toolset.__aenter__()
            # 连接成功，包装后返回（agent.iter 不会重复连接）
            toolsets.append(_PreconnectedToolset(toolset))
            logger.info("MCP toolset connected: %s → %s", name, entry.url)
        except Exception as e:
            logger.error("MCP toolset '%s' 连接失败，跳过: %s", name, e)

    return toolsets

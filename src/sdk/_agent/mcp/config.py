"""MCP 配置管理：从 mcp.json 加载/保存 MCP 服务器配置。

配置文件位置：{AGENT_FS_DIR}/mcp.json
格式：
{
  "mcpServers": {
    "server-name": {
      "url": "http://localhost:8199/mcp",
      "headers": {"Authorization": "Bearer xxx"}  // 可选
    }
  }
}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.sdk._common.filesystem_backend import BackendProtocol

logger: logging.Logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = "/mcp.json"


@dataclass
class McpServerEntry:
    """单个 MCP 服务器配置。"""

    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class McpConfig:
    """MCP 配置集合。"""

    servers: dict[str, McpServerEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 可存储的 dict。"""
        return {
            "mcpServers": {
                name: {
                    "url": entry.url,
                    **({"headers": entry.headers} if entry.headers else {}),
                }
                for name, entry in self.servers.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpConfig:
        """从 dict 反序列化。"""
        config = cls()
        mcp_servers = data.get("mcpServers", {})
        for name, server_data in mcp_servers.items():
            if isinstance(server_data, dict) and "url" in server_data:
                config.servers[name] = McpServerEntry(
                    name=name,
                    url=server_data["url"],
                    headers=server_data.get("headers", {}),
                )
        return config


async def load_mcp_config(backend: BackendProtocol) -> McpConfig:
    """从 agent_fs backend 加载 MCP 配置。"""
    if not await backend.aexists(MCP_CONFIG_PATH):
        return McpConfig()

    try:
        # 使用 adownload_files 获取原始字节内容（aread 会添加行号，无法 JSON 解析）
        results = await backend.adownload_files([MCP_CONFIG_PATH])
        if not results or results[0].error or results[0].content is None:
            return McpConfig()
        data = json.loads(results[0].content.decode("utf-8"))
        return McpConfig.from_dict(data)
    except Exception as e:
        logger.warning("加载 mcp.json 失败: %s", e)
        return McpConfig()


async def save_mcp_config(backend: BackendProtocol, config: McpConfig) -> None:
    """保存 MCP 配置到 agent_fs backend。"""
    content = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
    await backend.aupload_files([(MCP_CONFIG_PATH, content.encode("utf-8"))])

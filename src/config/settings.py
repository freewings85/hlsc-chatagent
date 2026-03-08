"""配置管理：从环境变量加载所有配置"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from dotenv import load_dotenv

if TYPE_CHECKING:
    from src.agent.compact.config import CompactConfig
    from src.common.filesystem_backend import BackendProtocol

load_dotenv()


@dataclass
class LLMConfig:
    """LLM 连接配置"""

    llm_type: str = field(default_factory=lambda: os.getenv("LLM_TYPE", "azure"))
    # Azure
    azure_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    azure_api_key: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", ""))
    azure_api_version: str = field(default_factory=lambda: os.getenv("AZURE_API_VERSION", "2024-12-01-preview"))
    azure_deployment_name: str = field(default_factory=lambda: os.getenv("AZURE_DEPLOYMENT_NAME", ""))
    # OpenAI
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    # 通用
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))


@dataclass
class UserFsConfig:
    """用户级存储配置（session 数据、对话历史等按用户隔离的文件）"""

    user_fs_dir: str = field(default_factory=lambda: os.getenv("USER_FS_DIR", "data"))

    @property
    def sessions_dir(self) -> str:
        return os.path.join(self.user_fs_dir, "sessions")


@dataclass
class AgentFsConfig:
    """Agent 文件资源配置（skills、agent.md 等全局共享文件）

    与用户数据（USER_FS_DIR）隔离，集群部署时所有节点共享此目录。
    目录结构：
      {AGENT_FS_DIR}/
      ├── skills/        # 已安装的 skill
      ├── agent.md       # 系统 prompt 配置
      └── ...            # 将来可能有更多资源
    """

    agent_fs_dir: str = field(default_factory=lambda: os.getenv("AGENT_FS_DIR", ".chatagent"))


@dataclass
class ServerConfig:
    """服务器配置"""

    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "8100")))


# 延迟初始化单例
_llm_config: Optional[LLMConfig] = None
_user_fs_config: Optional[UserFsConfig] = None
_agent_fs_config: Optional[AgentFsConfig] = None
_server_config: Optional[ServerConfig] = None
_compact_config: Optional["CompactConfig"] = None
_user_fs_backend: Optional["BackendProtocol"] = None
_agent_fs_backend: Optional["BackendProtocol"] = None


def get_llm_config() -> LLMConfig:
    """获取 LLM 配置"""
    global _llm_config
    if _llm_config is None:
        _llm_config = LLMConfig()
    return _llm_config


def get_user_fs_config() -> UserFsConfig:
    """获取用户级存储配置"""
    global _user_fs_config
    if _user_fs_config is None:
        _user_fs_config = UserFsConfig()
    return _user_fs_config


def get_agent_fs_config() -> AgentFsConfig:
    """获取 Agent 文件资源配置"""
    global _agent_fs_config
    if _agent_fs_config is None:
        _agent_fs_config = AgentFsConfig()
    return _agent_fs_config


def get_server_config() -> ServerConfig:
    """获取服务器配置"""
    global _server_config
    if _server_config is None:
        _server_config = ServerConfig()
    return _server_config


def get_compact_config() -> "CompactConfig":
    """获取压缩配置"""
    global _compact_config
    if _compact_config is None:
        from src.agent.compact.config import CompactConfig

        _compact_config = CompactConfig()
    return _compact_config


def get_user_fs_backend() -> "BackendProtocol":
    """获取用户级文件系统后端（全局单例，root=USER_FS_DIR，用于 session 数据）"""
    global _user_fs_backend
    if _user_fs_backend is None:
        from src.storage.local_backend import FilesystemBackend

        config = get_user_fs_config()
        _user_fs_backend = FilesystemBackend(root_dir=config.user_fs_dir, virtual_mode=True)
    return _user_fs_backend


# 向后兼容别名
get_backend = get_user_fs_backend
get_storage_config = get_user_fs_config


def get_agent_fs_backend() -> "BackendProtocol":
    """获取 Agent 文件资源后端（全局单例，root=AGENT_FS_DIR，用于 skills / agent.md 等）

    与用户 backend（root=USER_FS_DIR）隔离，集群部署时所有节点共享。
    """
    global _agent_fs_backend
    if _agent_fs_backend is None:
        from src.storage.local_backend import FilesystemBackend

        config = get_agent_fs_config()
        _agent_fs_backend = FilesystemBackend(root_dir=config.agent_fs_dir, virtual_mode=True)
    return _agent_fs_backend

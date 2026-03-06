"""配置管理：从环境变量加载所有配置"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from dotenv import load_dotenv

if TYPE_CHECKING:
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
class StorageConfig:
    """持久化存储配置"""

    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "data"))

    @property
    def sessions_dir(self) -> str:
        return os.path.join(self.data_dir, "sessions")


@dataclass
class ServerConfig:
    """服务器配置"""

    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "8100")))


# 延迟初始化单例
_llm_config: Optional[LLMConfig] = None
_storage_config: Optional[StorageConfig] = None
_server_config: Optional[ServerConfig] = None
_backend: Optional["BackendProtocol"] = None


def get_llm_config() -> LLMConfig:
    """获取 LLM 配置"""
    global _llm_config
    if _llm_config is None:
        _llm_config = LLMConfig()
    return _llm_config


def get_storage_config() -> StorageConfig:
    """获取存储配置"""
    global _storage_config
    if _storage_config is None:
        _storage_config = StorageConfig()
    return _storage_config


def get_server_config() -> ServerConfig:
    """获取服务器配置"""
    global _server_config
    if _server_config is None:
        _server_config = ServerConfig()
    return _server_config


def get_backend() -> "BackendProtocol":
    """获取文件系统后端（全局单例）"""
    global _backend
    if _backend is None:
        from src.storage.local_backend import FilesystemBackend

        config = get_storage_config()
        _backend = FilesystemBackend(root_dir=config.data_dir, virtual_mode=True)
    return _backend

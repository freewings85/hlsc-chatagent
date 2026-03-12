"""配置管理：从环境变量加载所有配置

正式入口（server.py）通过 src.common.nacos 统一加载环境变量（.env + Nacos 远程配置）。
测试等场景可能绕过 server.py 直接 import 本模块，此时 fallback 到 load_dotenv()。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from dotenv import load_dotenv

if TYPE_CHECKING:
    from src.agent.compact.config import CompactConfig
    from src.agent.memory.memory_context_service import MemoryContextService
    from src.agent.memory.memory_message_service import MemoryMessageService
    from src.agent.message.transcript_service import TranscriptService
    from src.common.filesystem_backend import BackendProtocol

# Fallback：如果 nacos 没有预先加载环境变量，确保 .env 至少被读取
# load_dotenv 不会覆盖已存在的环境变量，所以与 nacos 预加载不冲突
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
class LogfireConfig:
    """可观测性配置（Logfire / OpenTelemetry）"""

    enabled: bool = field(default_factory=lambda: os.getenv("LOGFIRE_ENABLED", "false").lower() == "true")
    endpoint: str = field(default_factory=lambda: os.getenv("LOGFIRE_ENDPOINT", ""))


@dataclass
class ServerConfig:
    """服务器配置"""

    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "8100")))


@dataclass
class TemporalConfig:
    """Temporal 配置"""

    enabled: bool = field(default_factory=lambda: os.getenv("TEMPORAL_ENABLED", "false").lower() == "true")
    host: str = field(default_factory=lambda: os.getenv("TEMPORAL_HOST", "localhost:7233"))
    interrupt_task_queue: str = field(default_factory=lambda: os.getenv("TEMPORAL_INTERRUPT_QUEUE", "interrupt-queue"))
    debug_mode: bool = field(default_factory=lambda: os.getenv("TEMPORAL_DEBUG_MODE", "false").lower() == "true")


@dataclass
class KafkaConfig:
    """Kafka 配置"""

    enabled: bool = field(default_factory=lambda: os.getenv("KAFKA_ENABLED", "false").lower() == "true")
    bootstrap_servers: str = field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    topic: str = field(default_factory=lambda: os.getenv("KAFKA_TOPIC", "chat-events"))


# 延迟初始化单例
_llm_config: Optional[LLMConfig] = None
_user_fs_config: Optional[UserFsConfig] = None
_agent_fs_config: Optional[AgentFsConfig] = None
_server_config: Optional[ServerConfig] = None
_temporal_config: Optional[TemporalConfig] = None
_kafka_config: Optional[KafkaConfig] = None
_compact_config: Optional["CompactConfig"] = None
_user_fs_backend: Optional["BackendProtocol"] = None
_agent_fs_backend: Optional["BackendProtocol"] = None
_memory_service_type: str = os.getenv("MEMORY_SERVICE_TYPE", "fs")  # "fs" | "sqlite"
_memory_message_service: Optional["MemoryMessageService"] = None
_memory_context_service: Optional["MemoryContextService"] = None
_transcript_service: Optional["TranscriptService"] = None


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


def get_temporal_config() -> TemporalConfig:
    """获取 Temporal 配置"""
    global _temporal_config
    if _temporal_config is None:
        _temporal_config = TemporalConfig()
    return _temporal_config


def get_kafka_config() -> KafkaConfig:
    """获取 Kafka 配置"""
    global _kafka_config
    if _kafka_config is None:
        _kafka_config = KafkaConfig()
    return _kafka_config


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


def get_memory_message_service() -> "MemoryMessageService":
    """获取会话消息工作集服务（全局单例，跨 request 复用缓存）

    通过 MEMORY_SERVICE_TYPE 环境变量选择实现：
    - "fs"     — FileMemoryMessageService（jsonl 文件持久化）
    - "sqlite" — SqliteMemoryMessageService（SQLite 持久化）
    """
    global _memory_message_service
    if _memory_message_service is None:
        if _memory_service_type == "sqlite":
            from src.agent.memory.sqlite_memory_message_service import SqliteMemoryMessageService

            _memory_message_service = SqliteMemoryMessageService(
                get_user_fs_config().user_fs_dir,
            )
        else:
            from src.agent.memory.file_memory_message_service import FileMemoryMessageService

            _memory_message_service = FileMemoryMessageService(get_user_fs_backend())
    return _memory_message_service


def get_memory_context_service() -> "MemoryContextService":
    """获取请求上下文工作集服务（全局单例）"""
    global _memory_context_service
    if _memory_context_service is None:
        from src.agent.memory.inmemory_context_service import InMemoryContextService

        from src.hlsc.hlsc_context import hlsc_context_formatter

        _memory_context_service = InMemoryContextService(formatter=hlsc_context_formatter)
    return _memory_context_service


def get_transcript_service() -> "TranscriptService":
    """获取 transcript 审计日志服务（全局单例）"""
    global _transcript_service
    if _transcript_service is None:
        from src.agent.message.transcript_service import TranscriptService

        _transcript_service = TranscriptService(get_user_fs_backend())
    return _transcript_service

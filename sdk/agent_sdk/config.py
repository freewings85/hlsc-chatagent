"""SDK 配置类：Agent 和 AgentApp 的所有配置项

参数分类原则：
- 直接传入：业务逻辑，每个 agent 不同（tools）
- service 接口：加载逻辑差异大，允许自定义实现（prompt_loader）
- config：框架核心能力，用户只调参数不换实现（model, memory, transcript, compact, skills）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Literal, cast

if TYPE_CHECKING:
    from agent_sdk._common.filesystem_backend import BackendProtocol

# tool 函数类型（与 AgentDeps 中的 ToolFunc 一致）
ToolFunc = Callable[..., Coroutine[Any, Any, str]]

# ============================================================
# 全局常量（从环境变量读取，所有代码通过这些常量访问）
# ============================================================

AGENT_NAME: str = os.getenv("AGENT_NAME", "agent")
"""Agent 名称（logfire / AgentApp / Agent 共用）"""

def _agent_fs_dir() -> str:
    from agent_sdk._config.settings import get_fs_config
    return get_fs_config().agent_fs_dir


AGENT_FS_DIR: str = os.getenv("AGENT_FS_DIR", ".chatagent")
"""Agent 工作目录（MCP、Skills 等）"""

MCP_CONFIG_PATH: str = os.path.join(AGENT_FS_DIR, "mcp.json")
"""MCP 配置文件路径"""

SKILL_DIRS: list[str] = [os.path.join(AGENT_FS_DIR, "fstools", "skills")]
"""Skill 目录列表（在 AGENT_FS_DIR/fstools/skills/ 下）"""


def get_agent_name() -> str:
    """获取 Agent 名称（兼容动态读取场景）。"""
    return os.getenv("AGENT_NAME", "agent")


@dataclass
class ModelConfig:
    """LLM 模型配置。

    框架内部根据此 config 构建 Pydantic AI Model。
    也可直接传入 pydantic_ai.models.Model 实例（测试/eval 场景）。
    """

    provider: str = field(default_factory=lambda: os.getenv("LLM_TYPE", "azure"))
    api_style: str = field(default_factory=lambda: os.getenv("LLM_API_STYLE", "chat"))
    # Azure
    azure_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    azure_api_key: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", ""))
    azure_api_version: str = field(default_factory=lambda: os.getenv("AZURE_API_VERSION", "2024-12-01-preview"))
    azure_deployment_name: str = field(default_factory=lambda: os.getenv("AZURE_DEPLOYMENT_NAME", ""))
    # OpenAI
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    model_name: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    # 通用
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))


@dataclass
class ToolConfig:
    """工具配置：支持手动 + 子集选取

    两种用法：
    1. 直接传 dict[str, ToolFunc]（最简 / 测试）
    2. ToolConfig（生产，手动 + 子集）
    """

    manual: dict[str, ToolFunc] | None = None
    include: list[str] | None = None  # 白名单
    exclude: list[str] | None = None  # 黑名单


@dataclass
class MemoryConfig:
    """消息工作集（messages.jsonl）配置"""

    backend: str = field(default_factory=lambda: os.getenv("MEMORY_SERVICE_TYPE", "fs"))
    data_dir: str = field(default_factory=lambda: _inner_storage_dir())


@dataclass
class TranscriptConfig:
    """审计日志（transcript.jsonl）配置"""

    enabled: bool = True
    data_dir: str = field(default_factory=lambda: _inner_storage_dir())


def _inner_storage_dir() -> str:
    from agent_sdk._config.settings import get_fs_config
    return get_fs_config().inner_storage_dir


@dataclass
class CompactConfig:
    """上下文压缩配置（复用现有 CompactConfig 的字段）"""

    context_window: int = field(default_factory=lambda: int(os.getenv("COMPACT_CONTEXT_WINDOW", "128000")))
    reserve_output_tokens: int = field(default_factory=lambda: int(os.getenv("COMPACT_RESERVE_OUTPUT", "8000")))
    reserve_working_tokens: int = field(default_factory=lambda: int(os.getenv("COMPACT_RESERVE_WORKING", "4000")))
    strategy: str = "full"


@dataclass
class StorageConfig:
    """存储后端配置

    当前支持：
    - "fs" — FilesystemBackend（本地文件系统）

    将来可扩展 "s3"、"pg" 等。
    """

    backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "fs"))


@dataclass
class AgentAppConfig:
    """AgentApp 部署容器配置"""

    name: str = field(default_factory=get_agent_name)
    description: str = ""
    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "8100")))
    temporal_enabled: bool = field(
        default_factory=lambda: os.getenv("TEMPORAL_ENABLED", "false").lower() == "true"
    )
    temporal_host: str = field(default_factory=lambda: os.getenv("TEMPORAL_HOST", "localhost:7233"))
    temporal_task_queue: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_INTERRUPT_QUEUE", "interrupt-queue")
    )
    chat_fs_backend_mode: Literal["session", "global"] = field(
        default_factory=lambda: cast(
            Literal["session", "global"],
            os.getenv("CHAT_FS_BACKEND_MODE", "session"),
        )
    )
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    a2a_skills: list[Any] | None = None  # list[AgentSkill]


# ============================================================
# Backend 工厂（全局单例）
# ============================================================

_storage_config: StorageConfig | None = None
_agent_fs_backend: BackendProtocol | None = None


def get_storage_config() -> StorageConfig:
    """获取存储配置"""
    global _storage_config
    if _storage_config is None:
        _storage_config = StorageConfig()
    return _storage_config


def _create_backend(root_dir: str) -> BackendProtocol:
    """根据 StorageConfig 创建 backend 实例"""
    config = get_storage_config()
    if config.backend == "fs":
        from agent_sdk._storage.local_backend import FilesystemBackend
        return FilesystemBackend(root_dir=root_dir, virtual_mode=True)
    raise ValueError(f"未知的 storage backend: {config.backend}")



def get_agent_fs_backend() -> BackendProtocol:
    """获取 Agent 级存储后端（全局单例，root=AGENT_FS_DIR）"""
    global _agent_fs_backend
    if _agent_fs_backend is None:
        _agent_fs_backend = _create_backend(AGENT_FS_DIR)
    return _agent_fs_backend


def create_session_backend(user_id: str, session_id: str) -> BackendProtocol:
    """为单个会话创建 fs_tools 后端（非单例，每次新建）"""
    from agent_sdk._config.settings import get_fs_config
    fs_tools_dir = get_fs_config().fs_tools_dir
    session_root = f"{fs_tools_dir}/{user_id}/sessions/{session_id}"
    return _create_backend(session_root)

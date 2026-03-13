"""SDK 配置类：Agent 和 AgentApp 的所有配置项

参数分类原则：
- 直接传入：业务逻辑，每个 agent 不同（tools）
- service 接口：加载逻辑差异大，允许自定义实现（prompt_loader）
- config：框架核心能力，用户只调参数不换实现（model, memory, transcript, compact, skills）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

# tool 函数类型（与 AgentDeps 中的 ToolFunc 一致）
ToolFunc = Callable[..., Coroutine[Any, Any, str]]


@dataclass
class ModelConfig:
    """LLM 模型配置。

    框架内部根据此 config 构建 Pydantic AI Model。
    也可直接传入 pydantic_ai.models.Model 实例（测试/eval 场景）。
    """

    provider: str = field(default_factory=lambda: os.getenv("LLM_TYPE", "azure"))
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
class McpConfig:
    """MCP 工具加载配置"""

    config_path: str | None = None  # ".mcp.json"


@dataclass
class ToolConfig:
    """工具配置：支持手动 + MCP + 子集选取

    三种用法：
    1. 直接传 dict[str, ToolFunc]（最简 / 测试）
    2. ToolConfig（生产，MCP + 手动 + 子集）
    3. 组合使用 manual + mcp_config + include/exclude
    """

    manual: dict[str, ToolFunc] | None = None
    mcp_config: McpConfig | None = None
    include: list[str] | None = None  # 白名单
    exclude: list[str] | None = None  # 黑名单


@dataclass
class MemoryConfig:
    """消息工作集（messages.jsonl）配置"""

    backend: str = field(default_factory=lambda: os.getenv("MEMORY_SERVICE_TYPE", "fs"))
    data_dir: str = field(default_factory=lambda: os.getenv("USER_FS_DIR", "data"))


@dataclass
class TranscriptConfig:
    """审计日志（transcript.jsonl）配置"""

    enabled: bool = True
    data_dir: str = field(default_factory=lambda: os.getenv("USER_FS_DIR", "data"))


@dataclass
class CompactConfig:
    """上下文压缩配置（复用现有 CompactConfig 的字段）"""

    context_window: int = field(default_factory=lambda: int(os.getenv("COMPACT_CONTEXT_WINDOW", "128000")))
    reserve_output_tokens: int = field(default_factory=lambda: int(os.getenv("COMPACT_RESERVE_OUTPUT", "8000")))
    reserve_working_tokens: int = field(default_factory=lambda: int(os.getenv("COMPACT_RESERVE_WORKING", "4000")))
    strategy: str = "full"


@dataclass
class SkillConfig:
    """Skill 系统配置"""

    skill_dirs: list[str] | None = None  # None → 不启用


@dataclass
class AgentAppConfig:
    """AgentApp 部署容器配置"""

    name: str = "Agent"
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
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    a2a_skills: list[Any] | None = None  # list[AgentSkill]

"""MainAgent 业务配置（从环境变量读取）"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEMO_PRICE_FINDER_URL: str = os.getenv("DEMO_PRICE_FINDER_URL", "http://localhost:8101")
"""DemoPriceFinder Subagent 的 A2A 地址"""

CODE_AGENT_URL: str = os.getenv("CODE_AGENT_URL", "http://localhost:8102")
"""CodeAgent Subagent 的 A2A 地址"""

DIAGNOSE_AGENT_URL: str = os.getenv("DIAGNOSE_AGENT_URL", "http://localhost:8103")
"""DiagnoseAgent Subagent 的 A2A 地址"""

CONFIRM_PROJECT_URL: str = os.getenv("CONFIRM_PROJECT_URL", "http://localhost:8104")
"""ConfirmProject Subagent 的 A2A 地址"""

RECOMMEND_PROJECT_URL: str = os.getenv("RECOMMEND_PROJECT_URL", "http://localhost:8105")
"""RecommendProject Subagent 的 A2A 地址"""


@dataclass
class ClassifyConfig:
    """场景识别模型配置（独立于主对话模型）。"""

    enabled: bool = field(
        default_factory=lambda: os.getenv("CLASSIFY_ENABLED", "true").lower() == "true"
    )
    provider: str = field(default_factory=lambda: os.getenv("CLASSIFY_LLM_TYPE", os.getenv("LLM_TYPE", "azure")))
    # Azure
    azure_endpoint: str = field(default_factory=lambda: os.getenv("CLASSIFY_AZURE_OPENAI_ENDPOINT", os.getenv("AZURE_OPENAI_ENDPOINT", "")))
    azure_api_key: str = field(default_factory=lambda: os.getenv("CLASSIFY_AZURE_OPENAI_API_KEY", os.getenv("AZURE_OPENAI_API_KEY", "")))
    azure_api_version: str = field(default_factory=lambda: os.getenv("CLASSIFY_AZURE_API_VERSION", os.getenv("AZURE_API_VERSION", "2024-12-01-preview")))
    azure_deployment_name: str = field(default_factory=lambda: os.getenv("CLASSIFY_AZURE_DEPLOYMENT_NAME", os.getenv("AZURE_DEPLOYMENT_NAME", "")))
    # OpenAI-compatible
    api_key: str = field(default_factory=lambda: os.getenv("CLASSIFY_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    base_url: str = field(default_factory=lambda: os.getenv("CLASSIFY_OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "")))
    model_name: str = field(default_factory=lambda: os.getenv("CLASSIFY_LLM_MODEL", os.getenv("LLM_MODEL", "")))
    # Common
    temperature: float = field(default_factory=lambda: float(os.getenv("CLASSIFY_LLM_TEMPERATURE", "0")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("CLASSIFY_LLM_MAX_RETRIES", "1")))

    # Classification context controls
    history_limit: int = field(default_factory=lambda: int(os.getenv("CLASSIFY_HISTORY_LIMIT", "10")))

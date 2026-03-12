"""ChatAgent SDK：两层 API 快速构建 Agent 服务

使用方式：

    # Subagent（最简）
    from src.sdk import Agent, AgentApp, AgentAppConfig, StaticPromptLoader

    agent = Agent(
        prompt_loader=StaticPromptLoader("你是 PriceFinder Agent..."),
        tools={"find_best_price": find_best_price_fn},
    )
    app = AgentApp(agent, AgentAppConfig(name="PriceFinder", port=8101))
    app.run()

    # 主 Agent
    from src.sdk import Agent, AgentApp, TemplatePromptLoader, ToolConfig, McpConfig

    agent = Agent(
        prompt_loader=TemplatePromptLoader(...),
        tools=ToolConfig(manual={...}, mcp_config=McpConfig(...)),
        compact_config=CompactConfig(context_window=128000),
        skill_config=SkillConfig(skill_dirs=["skills/"]),
    )
    app = AgentApp(agent, AgentAppConfig(name="MainAgent", port=8100))
    app.run()
"""

from src.sdk.agent import Agent
from src.sdk.agent_app import AgentApp
from src.sdk.config import (
    AgentAppConfig,
    CompactConfig,
    McpConfig,
    MemoryConfig,
    ModelConfig,
    SkillConfig,
    ToolConfig,
    TranscriptConfig,
)
from src.sdk.prompt_loader import (
    PromptLoader,
    PromptResult,
    StaticPromptLoader,
    TemplatePromptLoader,
)

__all__ = [
    # 核心
    "Agent",
    "AgentApp",
    # Config
    "AgentAppConfig",
    "CompactConfig",
    "McpConfig",
    "MemoryConfig",
    "ModelConfig",
    "SkillConfig",
    "ToolConfig",
    "TranscriptConfig",
    # Prompt
    "PromptLoader",
    "PromptResult",
    "StaticPromptLoader",
    "TemplatePromptLoader",
]

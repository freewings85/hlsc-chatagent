"""ChatAgent SDK：两层 API 快速构建 Agent 服务

使用方式：

    # Subagent（最简）
    from agent_sdk import Agent, AgentApp, AgentAppConfig, StaticPromptLoader

    agent = Agent(
        prompt_loader=StaticPromptLoader("你是一个 Agent..."),
        tools=ToolConfig(manual={"my_tool": my_tool_fn}),
    )
    app = AgentApp(agent, AgentAppConfig(description="..."))
    app.run()

    # 主 Agent
    from agent_sdk import Agent, AgentApp, TemplatePromptLoader, ToolConfig

    agent = Agent(
        prompt_loader=TemplatePromptLoader(...),
        tools=ToolConfig(manual={...}),
        compact_config=CompactConfig(context_window=128000),
    )
    app = AgentApp(agent, AgentAppConfig(description="..."))
    app.run()
"""

from agent_sdk.agent import Agent
from agent_sdk.agent_app import AgentApp
from agent_sdk.config import (
    AgentAppConfig,
    CompactConfig,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
    TranscriptConfig,
)
from agent_sdk.prompt_loader import (
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
    "MemoryConfig",
    "ModelConfig",
    "ToolConfig",
    "TranscriptConfig",
    # Prompt
    "PromptLoader",
    "PromptResult",
    "StaticPromptLoader",
    "TemplatePromptLoader",
]

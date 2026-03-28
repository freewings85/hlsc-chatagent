"""BusinessMapAgent Subagent 工厂：创建配置好的 AgentApp 实例。

启动时加载 BusinessMapService 到内存，并注入到各 tool 模块。
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from hlsc.services.business_map_service import BusinessMapService
from src.bm_context import BusinessMapContextFormatter
from src.config import get_business_map_dir
from src.prompt_loader import create_bm_prompt_loader
from src.tools import create_bm_tool_map

logger: logging.Logger = logging.getLogger(__name__)


def create_agent_app() -> AgentApp:
    """创建 BusinessMapAgent AgentApp。

    启动流程：
    1. 从配置路径加载 BusinessMapService
    2. 将 service 实例注入到各 tool 模块
    3. 创建 Agent 和 AgentApp
    """
    # 加载业务地图
    bm_dir = get_business_map_dir()
    logger.info("加载业务地图: %s", bm_dir)
    service: BusinessMapService = BusinessMapService()
    service.load(bm_dir)
    logger.info("业务地图加载完成")

    # 注入 service 到 tool 模块（使用 importlib 避免 __init__.py 的函数名遮蔽子模块）
    gbc_mod: ModuleType = importlib.import_module("src.tools.get_business_children")
    gbn_mod: ModuleType = importlib.import_module("src.tools.get_business_node")
    gbc_mod.set_service(service)
    gbn_mod.set_service(service)

    # 创建 Agent
    prompt_loader: object = create_bm_prompt_loader()
    tool_map: dict[str, object] = create_bm_tool_map()

    agent: Agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
        context_formatter=BusinessMapContextFormatter(),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="业务地图定位器 — 逐层导航业务地图，输出定位节点 ID",
        ),
    )

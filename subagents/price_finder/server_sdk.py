"""PriceFinder Subagent — 使用 SDK 重写版本。

启动方式（从项目根目录）：
    uv run python -m subagents.price_finder.server_sdk [--port 8101]

对比 server.py（旧版），本文件只需 ~30 行即可完成相同功能。
"""

from __future__ import annotations

import argparse
import logging

from a2a.types import AgentSkill

from src.sdk import Agent, AgentApp, AgentAppConfig, StaticPromptLoader
from subagents.price_finder.tools import (
    PRICE_FINDER_TOOLS,
    create_price_finder_tool_map,
)

logger = logging.getLogger(__name__)


_PRICE_FINDER_SYSTEM_PROMPT = """\
你是 PriceFinder Agent。你只有一个能力：调用 find_best_price_of_project 工具。

## 绝对规则（违反即失败）

1. 收到任何消息后，你必须**立即**调用 find_best_price_of_project 工具
2. 禁止不调用工具就回复用户
3. 禁止编造任何价格数据
4. 禁止向用户提问或要求澄清
5. 将用户消息中的项目描述直接作为 project_name 参数传给工具

## 流程

用户消息 → 调用 find_best_price_of_project(project_name=用户描述) → 返回工具结果
"""


agent = Agent(
    prompt_loader=StaticPromptLoader(_PRICE_FINDER_SYSTEM_PROMPT),
    tools=create_price_finder_tool_map(),
    agent_name="price_finder",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="PriceFinder Subagent Server (SDK)")
    parser.add_argument("--port", type=int, default=8101)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    app = AgentApp(
        agent,
        AgentAppConfig(
            name="PriceFinder",
            description="汽车维修项目最低价查询 Agent，支持比价和用户确认",
            host=args.host,
            port=args.port,
            a2a_skills=[
                AgentSkill(
                    id="find_best_price",
                    name="Find Best Price",
                    description="Search for the cheapest price for a car repair project and confirm with user",
                    tags=["price", "inquiry", "hitl"],
                ),
            ],
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

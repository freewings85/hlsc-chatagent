"""PriceFinder Subagent 独立服务。

启动方式（从项目根目录）：
    uv run python -m subagents.price_finder.server [--port 8101]

使用与主项目相同的 agent loop、事件系统、interrupt 机制。
通过 A2A 协议暴露端点，可被 main agent 调用。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

import uvicorn
from a2a.types import AgentSkill
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# Temporal client（lifespan 中初始化）
_temporal_client = None
_interrupt_worker = None


def _get_temporal_client():
    return _temporal_client


def _agent_factory(
    session_id: str, user_id: str, temporal_client: Any
) -> tuple:
    """创建 PriceFinder 专属的 agent + deps。"""
    from src.agent.deps import AgentDeps
    from src.agent.loop import create_agent
    from src.agent.model import create_model

    from subagents.price_finder.tools import (
        PRICE_FINDER_TOOLS,
        create_price_finder_tool_map,
    )

    model = create_model()
    agent = create_agent(model)
    deps = AgentDeps(
        session_id=session_id,
        user_id=user_id,
        available_tools=list(PRICE_FINDER_TOOLS),
        tool_map=create_price_finder_tool_map(),
        temporal_client=temporal_client,
    )
    return model, agent, deps


def create_app() -> FastAPI:
    """创建 PriceFinder FastAPI 应用。"""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _temporal_client, _interrupt_worker

        from src.config.settings import get_temporal_config

        config = get_temporal_config()
        if config.enabled:
            from temporalio.client import Client

            from src.agent.interrupt import create_interrupt_worker

            _temporal_client = await Client.connect(config.host)
            _interrupt_worker = create_interrupt_worker(
                _temporal_client,
                task_queue=config.interrupt_task_queue,
            )
            worker_task = asyncio.create_task(_interrupt_worker.run())
            logger.info(
                f"PriceFinder: Temporal worker started "
                f"(queue={config.interrupt_task_queue})"
            )
        else:
            worker_task = None
            logger.warning(
                "PriceFinder: Temporal disabled, "
                "find_best_price_of_project 的 interrupt 将不可用"
            )

        yield

        if _interrupt_worker is not None:
            await _interrupt_worker.shutdown()
        if worker_task is not None and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass
        _temporal_client = None
        _interrupt_worker = None

    app = FastAPI(
        title="PriceFinder Subagent",
        description="汽车项目最低价查询 Subagent（A2A 协议）",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "price_finder"}

    # 挂载 A2A 端点
    from src.server.a2a_adapter import mount_a2a

    mount_a2a(
        app,
        base_url="http://localhost:8101",
        temporal_client_getter=_get_temporal_client,
        agent_factory=_agent_factory,
        agent_card_name="PriceFinder",
        agent_card_description="汽车维修项目最低价查询 Agent，支持比价和用户确认",
        agent_card_skills=[
            AgentSkill(
                id="find_best_price",
                name="Find Best Price",
                description="Search for the cheapest price for a car repair project and confirm with user",
                tags=["price", "inquiry", "hitl"],
            ),
        ],
        rpc_url="/a2a",
    )

    return app


def main():
    parser = argparse.ArgumentParser(description="PriceFinder Subagent Server")
    parser.add_argument("--port", type=int, default=8101)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

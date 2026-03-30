"""Auctioneer：AgentApp（LLM 汇总）+ Temporal 调度端点。"""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from src.auctioneer_context import AuctioneerContextFormatter
from src.models import AuctionParams, AuctionStatus
from src.prompt_loader import create_auctioneer_prompt_loader
from src.tools import create_auctioneer_tool_map


def create_agent_app() -> AgentApp:
    """创建 Auctioneer AgentApp + Temporal 拍卖端点。"""
    prompt_loader: object = create_auctioneer_prompt_loader()
    tool_map: dict[str, object] = create_auctioneer_tool_map()

    agent: Agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
        context_formatter=AuctioneerContextFormatter(),
    )

    agent_app: AgentApp = AgentApp(
        agent,
        AgentAppConfig(
            description="拍卖师 — Temporal 定时轮询 + LLM 汇总分析",
        ),
    )

    _register_auction_routes(agent_app.app)

    return agent_app


def _register_auction_routes(app: object) -> None:
    """注册拍卖任务的 HTTP 端点（Temporal 版）。"""
    from temporalio.client import WorkflowHandle
    from src.temporal.client import TASK_QUEUE, get_client
    from src.temporal.workflows import AuctionWorkflow

    @app.post("/auction/start")
    async def start_auction(params: AuctionParams) -> dict[str, str]:
        """接受预定单，通过 Temporal 启动拍卖工作流。"""
        client = await get_client()
        task_id: str = f"auction-{uuid.uuid4().hex[:8]}"
        await client.start_workflow(
            AuctionWorkflow.run,
            params,
            id=task_id,
            task_queue=TASK_QUEUE,
        )
        return {
            "task_id": task_id,
            "status": "started",
            "message": "竞标任务已启动，10秒轮询一次，60秒后触发汇总",
        }

    @app.get("/auction/{task_id}/status")
    async def get_status(task_id: str) -> dict[str, object]:
        """实时查询轮询进度。"""
        client = await get_client()
        handle: WorkflowHandle = client.get_workflow_handle(task_id)
        try:
            result: dict[str, object] = await handle.query(AuctionWorkflow.get_status)
            return {"task_id": task_id, **result}
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"任务不存在或已过期: {e}")

    @app.get("/auction/{task_id}/result")
    async def get_result(task_id: str) -> dict[str, object]:
        """获取汇总结果（仅 COMPLETED 状态返回 recommendation）。"""
        client = await get_client()
        handle: WorkflowHandle = client.get_workflow_handle(task_id)
        try:
            result: dict[str, object] = await handle.query(AuctionWorkflow.get_status)
            if result["status"] != AuctionStatus.COMPLETED.value:
                raise HTTPException(status_code=202, detail="任务进行中，请稍后查询")
            return {"task_id": task_id, **result}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"任务不存在或已过期: {e}")

    # SDK 的 _build_fastapi 注册了 SPA 兜底路由 GET /{full_path:path}，
    # 它早于我们的 /auction/* GET 路由注册，会拦截所有 GET 请求。
    # 将 /auction/* 路由移到 SPA fallback 之前修正路由优先级。
    _move_auction_routes_before_spa(app)


def _move_auction_routes_before_spa(app: object) -> None:
    """将 /auction/* 路由移到 SPA catch-all (/{full_path:path}) 之前。"""
    routes: list = app.router.routes

    spa_idx: int = next(
        (i for i, r in enumerate(routes) if getattr(r, "path", "") == "/{full_path:path}"),
        -1,
    )
    if spa_idx < 0:
        return

    # auction 路由在 SPA fallback 之后（我们刚刚添加的）
    auction_routes: list = [
        r for r in routes[spa_idx + 1:]
        if getattr(r, "path", "").startswith("/auction")
    ]
    if not auction_routes:
        return

    # 从末尾移除，再插到 SPA fallback 前面
    for r in auction_routes:
        routes.remove(r)

    # 移除后 spa_idx 不变（因为被移除的路由都在 spa_idx 之后）
    for offset, r in enumerate(auction_routes):
        routes.insert(spa_idx + offset, r)

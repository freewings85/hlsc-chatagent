"""Auctioneer 启动入口。

在同一进程内同时运行：
  - FastAPI HTTP Server（uvicorn）
  - Temporal Auction Worker

启动方式：
    uv run python server.py
    uv run python server.py --port 8106
    ACTIVE=test uv run python server.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os


def main() -> None:
    from pathlib import Path

    log_dir: Path = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler: logging.FileHandler = logging.FileHandler(log_dir / "auctioneer.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(), file_handler])

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    args = parser.parse_args()

    from agent_sdk._common.nacos import register_service, deregister_service

    if args.port is not None:
        os.environ["SERVER_PORT"] = str(args.port)
    if args.host is not None:
        os.environ["SERVER_HOST"] = args.host

    register_service()

    from agent_sdk._config.settings import LogfireConfig
    from agent_sdk.config import get_agent_name

    logfire_config = LogfireConfig()
    if logfire_config.enabled:
        import logfire

        if logfire_config.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from agent_sdk._config.otel import patch_pydantic_ai_json_dumps

            patch_pydantic_ai_json_dumps()
            logfire.configure(
                service_name=get_agent_name(),
                send_to_logfire=False,
                scrubbing=False,
                additional_span_processors=[
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=logfire_config.endpoint)),
                ],
            )
        else:
            logfire.configure(service_name=get_agent_name())
        logfire.instrument_pydantic_ai()
        logfire.instrument_httpx(
            capture_request_body=logfire_config.capture_http_body,
            capture_response_body=logfire_config.capture_http_body,
        )

    from src.app import create_agent_app

    agent_app = create_agent_app()

    try:
        asyncio.run(_run(agent_app))
    finally:
        deregister_service()


async def _run(agent_app: object) -> None:
    """在同一 event loop 内并行运行 HTTP Server 和 Temporal Worker。"""
    import uvicorn
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    from src.temporal.activities import (
        broadcast_offers_activity,
        cancel_order_activity,
        commit_order_activity,
        poll_offers_activity,
        select_best_offer_activity,
    )
    from src.temporal.client import TASK_QUEUE, get_client
    from src.temporal.workflows import AuctionWorkflow

    host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    port: int = int(os.getenv("SERVER_PORT", "8100"))

    # 启动 Temporal Worker
    client = await get_client()
    worker: Worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AuctionWorkflow],
        activities=[
            poll_offers_activity,
            broadcast_offers_activity,
            select_best_offer_activity,
            commit_order_activity,
            cancel_order_activity,
        ],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )
    worker_task: asyncio.Task = asyncio.create_task(worker.run())
    logging.info("Auction Worker 已启动，监听队列 [%s]", TASK_QUEUE)

    # 启动 HTTP Server
    config: uvicorn.Config = uvicorn.Config(agent_app.app, host=host, port=port)
    server: uvicorn.Server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        logging.info("Auction Worker 已停止")


if __name__ == "__main__":
    main()

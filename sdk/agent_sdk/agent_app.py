"""AgentApp：部署容器，将 Agent 包装为可运行的 HTTP 服务

自动提供的端点：
- GET  /health
- POST /chat/stream (SSE)
- POST /chat/async (Kafka 异步)
- POST /chat/stop
- POST /chat/interrupt-reply
- GET  /.well-known/agent.json (A2A)
- POST /a2a (A2A JSON-RPC)

使用方式：
    from agent_sdk import Agent, AgentApp, AgentAppConfig, StaticPromptLoader

    agent = Agent(prompt_loader=StaticPromptLoader("你好"), tools={...})
    app = AgentApp(agent, AgentAppConfig(name="MyAgent", port=8101))
    app.run()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_sdk.agent import Agent
from agent_sdk.config import AgentAppConfig

logger = logging.getLogger(__name__)


class AgentApp:
    """部署容器：将 Agent 包装为可运行的 HTTP 服务"""

    def __init__(
        self,
        agent: Agent,
        config: AgentAppConfig | None = None,
    ) -> None:
        self._agent = agent
        self._config = config or AgentAppConfig()
        self._temporal_client: Any = None
        self._interrupt_worker: Any = None
        # 运行中的任务注册表：task_id → asyncio.Task
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self.app = self._build_fastapi()

    def _build_fastapi(self) -> Any:
        """构建 FastAPI 应用"""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse, StreamingResponse

        config = self._config
        agent = self._agent

        @asynccontextmanager
        async def lifespan(app: FastAPI):  # type: ignore[type-arg]
            # Temporal 初始化
            if config.temporal_enabled:
                try:
                    from temporalio.client import Client
                    from agent_sdk._agent.interrupt import create_interrupt_worker

                    self._temporal_client = await Client.connect(config.temporal_host)
                    self._interrupt_worker = create_interrupt_worker(
                        self._temporal_client,
                        task_queue=config.temporal_task_queue,
                    )
                    asyncio.create_task(self._interrupt_worker.run())
                    logger.info(
                        f"{config.name}: Temporal worker started "
                        f"(queue={config.temporal_task_queue})"
                    )
                except Exception as exc:
                    logger.warning(f"{config.name}: Temporal init failed: {exc}")
            else:
                logger.warning(f"{config.name}: Temporal disabled")

            yield

            # Shutdown
            if self._interrupt_worker is not None:
                await self._interrupt_worker.shutdown()
            self._temporal_client = None
            self._interrupt_worker = None

        fastapi_app = FastAPI(
            title=config.name,
            description=config.description,
            version="0.1.0",
            lifespan=lifespan,
        )

        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Health
        @fastapi_app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok", "service": config.name}

        # SSE Chat Stream
        @fastapi_app.post("/chat/stream")
        async def chat_stream(request: dict[str, Any]) -> StreamingResponse:
            from agent_sdk._event.event_emitter import EventEmitter
            from agent_sdk._event.event_model import EventModel
            from agent_sdk._event.event_type import EventType

            session_id = request.get("session_id", "default")
            user_id = request.get("user_id", "anonymous")
            message = request.get("message", "")
            context = request.get("context")

            queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
            emitter = EventEmitter(queue)

            loop_task = asyncio.create_task(
                agent.run(
                    message,
                    user_id=user_id,
                    session_id=session_id,
                    emitter=emitter,
                    temporal_client=self._temporal_client,
                    request_context=context,
                ),
                name=f"agent-loop-{session_id}",
            )

            task_id: str = f"stream-{session_id}-{id(loop_task)}"
            self._running_tasks[task_id] = loop_task

            def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
                queue.put_nowait(None)

            loop_task.add_done_callback(_ensure_sentinel)

            async def generate():  # type: ignore[return]
                try:
                    start_event = EventModel(
                        session_id=session_id,
                        request_id="",
                        type=EventType.CHAT_REQUEST_START,
                        data={"task_id": task_id},
                    )
                    yield f"event: {start_event.type.value}\ndata: {start_event.to_json()}\n\n"
                    while True:
                        event = await queue.get()
                        if event is None:
                            break
                        yield f"event: {event.type.value}\ndata: {event.to_json()}\n\n"
                except (GeneratorExit, asyncio.CancelledError):
                    pass
                finally:
                    self._running_tasks.pop(task_id, None)
                    if not loop_task.done():
                        loop_task.cancel()

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Async Chat（Kafka）
        @fastapi_app.post("/chat/async")
        async def chat_async(request: dict[str, Any]) -> JSONResponse:
            from agent_sdk._config.settings import get_kafka_config
            from agent_sdk._event.event_emitter import EventEmitter
            from agent_sdk._event.event_model import EventModel
            from agent_sdk._event.event_sinker_kafka import KafkaSinker, get_kafka_producer

            kafka_config = get_kafka_config()
            if not kafka_config.enabled:
                return JSONResponse(
                    status_code=503,
                    content={"error": "Kafka 未启用，请设置 KAFKA_ENABLED=true"},
                )

            session_id: str = request.get("session_id", "default")
            user_id: str = request.get("user_id", "anonymous")
            message: str = request.get("message", "")
            context: Any = request.get("context")

            producer = await get_kafka_producer()
            sinker = KafkaSinker(producer, kafka_config.topic)

            queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
            emitter = EventEmitter(queue)

            loop_task: asyncio.Task[None] = asyncio.create_task(
                agent.run(
                    message,
                    user_id=user_id,
                    session_id=session_id,
                    emitter=emitter,
                    temporal_client=self._temporal_client,
                    request_context=context,
                ),
                name=f"agent-loop-async-{session_id}",
            )

            # 生成 task_id 用于外部追踪
            task_id: str = f"async-{session_id}-{id(loop_task)}"
            self._running_tasks[task_id] = loop_task

            # 后台转发：从 emitter queue 读事件，通过 KafkaSinker 发到 Kafka
            async def _forward_to_kafka() -> None:
                try:
                    while True:
                        event: EventModel | None = await queue.get()
                        if event is None:
                            break
                        await sinker.send(event)
                except Exception:
                    logger.exception("Kafka 转发异常")
                finally:
                    self._running_tasks.pop(task_id, None)

            asyncio.create_task(
                _forward_to_kafka(),
                name=f"kafka-forward-{task_id}",
            )

            def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
                queue.put_nowait(None)

            loop_task.add_done_callback(_ensure_sentinel)

            return JSONResponse({"status": "accepted", "task_id": task_id})

        # Stop
        @fastapi_app.post("/chat/stop")
        async def chat_stop(request: dict[str, Any]) -> JSONResponse:
            task_id: str = request.get("task_id", "")
            loop_task = self._running_tasks.get(task_id)
            if loop_task is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "任务不存在或已结束"},
                )
            if not loop_task.done():
                loop_task.cancel()
            self._running_tasks.pop(task_id, None)
            return JSONResponse({"status": "cancelled", "task_id": task_id})

        # Interrupt Reply
        @fastapi_app.post("/chat/interrupt-reply")
        async def interrupt_reply(request: dict[str, Any]) -> JSONResponse:
            from agent_sdk._agent.interrupt import is_interrupt_active, resume
            interrupt_key = request.get("interrupt_key", "")
            reply = request.get("reply", "")
            reply_data = reply if isinstance(reply, dict) else {"reply": reply}

            if not is_interrupt_active(interrupt_key):
                try:
                    await resume(self._temporal_client, interrupt_key, reply_data)
                except Exception:
                    pass
                return JSONResponse(
                    status_code=410,
                    content={"error": "该对话已失效（服务重启），请重新发送消息",
                             "interrupt_key": interrupt_key},
                )

            try:
                # client=None 时走内存模式
                await resume(self._temporal_client, interrupt_key, reply_data)
                return JSONResponse({"status": "ok", "interrupt_key": interrupt_key})
            except Exception as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

        # 管理 API（skills / prompts / MCP）
        from agent_sdk._server.skill_api import router as skill_router
        from agent_sdk._server.prompt_api import router as prompt_router
        from agent_sdk._server.mcp_api import router as mcp_router

        fastapi_app.include_router(skill_router)
        fastapi_app.include_router(prompt_router)
        fastapi_app.include_router(mcp_router)

        # A2A 端点
        self._mount_a2a(fastapi_app)

        # Web 静态文件（公用前端）
        self._mount_web(fastapi_app)

        return fastapi_app

    def _mount_web(self, fastapi_app: Any) -> None:
        """挂载 Web 静态文件（公用前端）"""
        from pathlib import Path

        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles

        # 从项目根目录查找 web/dist
        # 优先使用环境变量，否则从 sdk/agent_sdk/ 向上找项目根
        import os

        web_dir = os.getenv("WEB_DIR")
        if web_dir:
            web_path = Path(web_dir)
        else:
            # sdk/agent_sdk/agent_app.py → parent=agent_sdk/ → parent=sdk/ → parent=项目根
            web_path = Path(__file__).parent.parent.parent / "web"

        dist_dir = web_path / "dist"

        @fastapi_app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            dist_html = dist_dir / "index.html"
            if dist_html.exists():
                return HTMLResponse(content=dist_html.read_text(encoding="utf-8"))
            dev_html = web_path / "index.html"
            if dev_html.exists():
                return HTMLResponse(content=dev_html.read_text(encoding="utf-8"))
            return HTMLResponse(content="<h1>web/index.html not found</h1>", status_code=404)

        if dist_dir.is_dir() and (dist_dir / "assets").is_dir():
            fastapi_app.mount(
                "/assets",
                StaticFiles(directory=str(dist_dir / "assets")),
                name="static-assets",
            )

        @fastapi_app.get("/{full_path:path}", response_class=HTMLResponse)
        async def spa_fallback(full_path: str) -> HTMLResponse:
            dist_html = dist_dir / "index.html"
            if dist_html.exists():
                return HTMLResponse(content=dist_html.read_text(encoding="utf-8"))
            return HTMLResponse(content="", status_code=404)

    def _mount_a2a(self, fastapi_app: Any) -> None:
        """挂载 A2A 协议端点"""
        try:
            from agent_sdk._server.a2a_adapter import mount_a2a

            config = self._config
            mount_a2a(
                fastapi_app,
                agent=self._agent,
                base_url=f"http://localhost:{config.port}",
                temporal_client_getter=lambda: self._temporal_client,
                agent_card_name=config.name,
                agent_card_description=config.description,
                agent_card_skills=config.a2a_skills,
            )
        except ImportError:
            logger.warning("A2A adapter not available, skipping A2A endpoints")

    def run(self) -> None:
        """启动服务（CLI 入口）"""
        import uvicorn

        uvicorn.run(
            self.app,
            host=self._config.host,
            port=self._config.port,
        )

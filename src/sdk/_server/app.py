"""FastAPI 应用"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.sdk._server.request import AsyncChatRequest, ChatRequest, InterruptReplyRequest, StopRequest
from src.sdk._server.mcp_api import router as mcp_router
from src.sdk._server.prompt_api import router as prompt_router
from src.sdk._server.skill_api import router as skill_router

logger: logging.Logger = logging.getLogger(__name__)

# 运行中的任务注册表：task_id → (SessionRequestTask, asyncio.Task)
_running_tasks: dict[str, tuple[object, asyncio.Task[None]]] = {}

# Temporal client（lifespan 中初始化）
_temporal_client = None
_interrupt_worker = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭 Temporal Worker。"""
    global _temporal_client, _interrupt_worker

    from src.sdk._config.settings import get_temporal_config

    config = get_temporal_config()
    if config.enabled:
        from temporalio.client import Client

        from src.sdk._agent.interrupt import create_interrupt_worker

        _temporal_client = await Client.connect(config.host)
        _interrupt_worker = create_interrupt_worker(
            _temporal_client,
            task_queue=config.interrupt_task_queue,
        )
        # Worker 作为后台任务运行
        worker_task = asyncio.create_task(_interrupt_worker.run())
        logger.info(f"Temporal interrupt worker started (queue={config.interrupt_task_queue})")
    else:
        worker_task = None
        logger.warning("Temporal disabled, ask_user 工具将不可用")

    yield

    # Shutdown
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


app: FastAPI = FastAPI(
    title="ChatAgent API",
    description="通用对话 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（允许 Vite dev server 跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 管理 API
app.include_router(skill_router)
app.include_router(prompt_router)
app.include_router(mcp_router)


def _get_temporal_client():
    """获取 Temporal client（None 时 ask_user 报错）。"""
    return _temporal_client


# A2A 协议端点
from src.sdk._server.a2a_adapter import mount_a2a

mount_a2a(app, temporal_client_getter=_get_temporal_client)

_WEB_DIR: Path = Path(__file__).parent.parent.parent / "web"
_DIST_DIR: Path = _WEB_DIR / "dist"


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查"""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """测试 UI 主页（优先使用 dist 构建产物）"""
    dist_html = _DIST_DIR / "index.html"
    if dist_html.exists():
        return HTMLResponse(content=dist_html.read_text(encoding="utf-8"))
    dev_html = _WEB_DIR / "index.html"
    if dev_html.exists():
        return HTMLResponse(content=dev_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>web/index.html 不存在</h1>", status_code=404)


# 静态资源（JS/CSS）从 dist/assets/ 提供
if _DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="static-assets")


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str) -> HTMLResponse:
    """SPA 路由回退：非 API 路径返回 index.html，由前端路由处理。"""
    dist_html = _DIST_DIR / "index.html"
    if dist_html.exists():
        return HTMLResponse(content=dist_html.read_text(encoding="utf-8"))
    dev_html = _WEB_DIR / "index.html"
    if dev_html.exists():
        return HTMLResponse(content=dev_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>web/index.html 不存在</h1>", status_code=404)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE 流式对话接口。

    事件格式：
        event: {type}
        data: {json}
        <空行>

    事件类型：text / tool_call_start / tool_call_args / tool_result /
              interrupt / error / chat_request_end
    """
    from src.sdk._agent.deps import AgentDeps
    from src.sdk._agent.loop import create_agent, run_main_agent
    from src.sdk._agent.model import create_model
    from src.sdk._agent.tools import ALL_FS_TOOLS, create_default_tool_map
    from src.sdk._common.session_request_task import SessionRequestTask
    from src.sdk._event.event_emitter import EventEmitter
    from src.sdk._event.event_model import EventModel
    from src.sdk._event.event_sinker_sse import SseSinker
    from src.sdk._event.event_type import EventType

    # Emitter 和 SSE generator 共享同一个 queue：
    # run_agent_loop → emitter.emit() → queue → SSE generator
    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter: EventEmitter = EventEmitter(queue)
    sinker: SseSinker = SseSinker(queue)  # 供 SessionRequestTask 要求，实际不被 loop 调用

    task: SessionRequestTask = SessionRequestTask(
        session_id=request.session_id,
        message=request.message,
        user_id=request.user_id,
        sinker=sinker,
        context=request.context,
    )

    model = create_model()
    agent = create_agent(model)
    deps: AgentDeps = AgentDeps(
        session_id=request.session_id,
        user_id=request.user_id,
        available_tools=list(ALL_FS_TOOLS),
        tool_map=create_default_tool_map(),
        temporal_client=_get_temporal_client(),
    )

    # 后台运行 Agent Loop，前台 SSE generator 消费事件
    loop_task: asyncio.Task[None] = asyncio.create_task(
        run_main_agent(emitter, task, agent, deps),
        name=f"agent-loop-{task.task_id}",
    )
    _running_tasks[task.task_id] = (task, loop_task)

    # loop_task 完成（正常或被取消）后确保 queue 有 sentinel，
    # 否则 SSE generator 会永远阻塞在 queue.get()
    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    async def generate() -> object:
        try:
            start_event = EventModel(
                session_id=task.session_id,
                request_id=task.request_id,
                type=EventType.CHAT_REQUEST_START,
                data={"task_id": task.task_id},
            )
            yield f"event: {start_event.type.value}\ndata: {start_event.to_json()}\n\n"
            while True:
                event: EventModel | None = await queue.get()
                if event is None:
                    break
                yield f"event: {event.type.value}\ndata: {event.to_json()}\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            task.cancelled = True
        finally:
            _running_tasks.pop(task.task_id, None)
            if not loop_task.done():
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat/stop")
async def chat_stop(request: StopRequest) -> JSONResponse:
    """停止正在运行的对话任务。"""
    entry = _running_tasks.get(request.task_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "任务不存在或已结束"})

    task_obj, loop_task = entry
    task_obj.cancelled = True  # type: ignore[union-attr]
    if not loop_task.done():
        loop_task.cancel()

    return JSONResponse({"status": "cancelled", "task_id": request.task_id})


@app.post("/chat/interrupt-reply")
async def interrupt_reply(request: InterruptReplyRequest) -> JSONResponse:
    """回复一个等待中的 interrupt，恢复 agent 执行。

    前端收到 interrupt 事件后，用户操作完毕调用此接口。
    interrupt_key 来自 interrupt 事件的 data.interrupt_key 字段。
    """
    if _temporal_client is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Temporal 未启用，无法处理 interrupt reply"},
        )

    from src.sdk._agent.interrupt import is_interrupt_active, resume

    reply_data = request.reply if isinstance(request.reply, dict) else {"reply": request.reply}

    # 检查 interrupt 是否在当前进程中活跃
    # 不活跃 = server 重启过，agent loop 已丢失
    if not is_interrupt_active(request.interrupt_key):
        # 仍然尝试完成 Temporal workflow（清理资源），但告知前端已失效
        try:
            await resume(_temporal_client, request.interrupt_key, reply_data)
        except Exception:
            pass  # workflow 可能已不存在，忽略
        return JSONResponse(
            status_code=410,
            content={
                "error": "该对话已失效（服务重启），请重新发送消息",
                "interrupt_key": request.interrupt_key,
            },
        )

    try:
        await resume(_temporal_client, request.interrupt_key, reply_data)
        return JSONResponse({"status": "ok", "interrupt_key": request.interrupt_key})
    except Exception as exc:
        logger.warning(f"interrupt-reply failed: {exc}")
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "interrupt_key": request.interrupt_key},
        )


@app.post("/chat/async")
async def chat_async(request: AsyncChatRequest) -> JSONResponse:
    """异步对话接口：立即返回 task_id，事件通过 Kafka 推送。

    需要 KAFKA_ENABLED=true 才可用。
    """
    from src.sdk._agent.deps import AgentDeps
    from src.sdk._agent.loop import create_agent, run_main_agent
    from src.sdk._agent.model import create_model
    from src.sdk._agent.tools import ALL_FS_TOOLS, create_default_tool_map
    from src.sdk._common.session_request_task import SessionRequestTask
    from src.sdk._config.settings import get_kafka_config
    from src.sdk._event.event_emitter import EventEmitter
    from src.sdk._event.event_model import EventModel
    from src.sdk._event.event_sinker_kafka import KafkaSinker, get_kafka_producer

    kafka_config = get_kafka_config()
    if not kafka_config.enabled:
        return JSONResponse(
            status_code=503,
            content={"error": "Kafka 未启用，请设置 KAFKA_ENABLED=true"},
        )

    producer = await get_kafka_producer()
    sinker = KafkaSinker(producer, kafka_config.topic)

    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter = EventEmitter(queue)

    task = SessionRequestTask(
        session_id=request.session_id,
        message=request.message,
        user_id=request.user_id,
        sinker=sinker,
        context=request.context,
    )

    model = create_model()
    agent = create_agent(model)
    deps = AgentDeps(
        session_id=request.session_id,
        user_id=request.user_id,
        available_tools=list(ALL_FS_TOOLS),
        tool_map=create_default_tool_map(),
        temporal_client=_get_temporal_client(),
    )

    loop_task = asyncio.create_task(
        run_main_agent(emitter, task, agent, deps),
        name=f"agent-loop-async-{task.task_id}",
    )
    _running_tasks[task.task_id] = (task, loop_task)

    # 后台转发：从 emitter queue 读事件，通过 KafkaSinker 发到 Kafka
    async def _forward_to_kafka() -> None:
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                await sinker.send(event)
        except Exception:
            logger.exception("Kafka 转发异常")
        finally:
            _running_tasks.pop(task.task_id, None)

    asyncio.create_task(
        _forward_to_kafka(),
        name=f"kafka-forward-{task.task_id}",
    )

    # loop_task 完成后确保 queue 有 sentinel
    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    return JSONResponse({"status": "accepted", "task_id": task.task_id})

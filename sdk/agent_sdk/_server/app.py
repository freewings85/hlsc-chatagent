"""FastAPI 应用"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent_sdk._server.request import AsyncChatRequest, ChatRequest, InterruptReplyRequest, StopRequest
from agent_sdk._server.mcp_api import router as mcp_router
from agent_sdk._server.prompt_api import router as prompt_router
from agent_sdk._server.skill_api import router as skill_router

logger: logging.Logger = logging.getLogger(__name__)

# 运行中的任务注册表：task_id → (SessionRequestTask, asyncio.Task)
_running_tasks: dict[str, tuple[object, asyncio.Task[None]]] = {}

# Temporal client（lifespan 中初始化）
_temporal_client = None
_interrupt_worker = None

# Lazy Agent 实例（standalone app 场景，使用默认工具集）
_agent_instance = None


def _get_agent():
    """获取默认 Agent 实例（lazy 创建）"""
    global _agent_instance
    if _agent_instance is None:
        from agent_sdk import Agent, ToolConfig
        from agent_sdk._agent.tools import create_default_tool_map
        from agent_sdk.prompt_loader import StaticPromptLoader

        _agent_instance = Agent(
            prompt_loader=StaticPromptLoader(
                "You are a helpful assistant.\n"
                "If user explicitly asks to use a tool, you should call that tool.\n"
                "For file operations (read/write/edit/glob/grep/bash), prefer tool calls over guessing.\n"
            ),
            tools=ToolConfig(manual=create_default_tool_map()),
        )
    return _agent_instance


def _get_temporal_client():
    return _temporal_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭 Temporal Worker。"""
    global _temporal_client, _interrupt_worker

    from agent_sdk._config.settings import get_temporal_config

    config = get_temporal_config()
    if config.enabled:
        from temporalio.client import Client

        from agent_sdk._agent.interrupt import create_interrupt_worker

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
        logger.info("Temporal disabled, interrupt 使用内存模式（进程重启后丢失）")

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
    """获取 Temporal client（None 时 call_interrupt 报错）。"""
    return _temporal_client


# A2A 协议端点
from agent_sdk._server.a2a_adapter import mount_a2a

mount_a2a(app, temporal_client_getter=_get_temporal_client)

_WEB_DIR: Path = Path(__file__).parent.parent.parent.parent / "web"
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


def _resolve_trace_context(raw_request: Request) -> tuple[str, object | None]:
    """从请求 header 提取 OTel trace context。

    Returns:
        (request_id, parent_otel_context)
        - request_id: trace_id 字符串，无 traceparent 时回退到 uuid
        - parent_otel_context: OTel Context 对象，传给 agent.run() 实现 trace 串联
    """
    from opentelemetry.propagate import extract
    from opentelemetry.trace import INVALID_TRACE_ID, format_trace_id, get_current_span

    ctx = extract(dict(raw_request.headers))
    trace_id: int = get_current_span(ctx).get_span_context().trace_id
    if trace_id != INVALID_TRACE_ID:
        return format_trace_id(trace_id), ctx
    return uuid.uuid4().hex, None


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, raw_request: Request) -> StreamingResponse:
    """SSE 流式对话接口。

    事件格式：
        event: {type}
        data: {json}
        <空行>

    事件类型：text / tool_call_start / tool_call_args / tool_result /
              interrupt / error / chat_request_end
    """
    from agent_sdk._event.event_emitter import EventEmitter
    from agent_sdk._event.event_model import EventModel
    from agent_sdk._event.event_type import EventType
    from agent_sdk._config.settings import get_fs_tools_backend

    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter: EventEmitter = EventEmitter(queue)

    agent = _get_agent()
    request_id, parent_otel_context = _resolve_trace_context(raw_request)
    task_id: str = f"{request.session_id}-{id(request)}"

    loop_task: asyncio.Task[None] = asyncio.create_task(
        agent.run(
            message=request.message,
            user_id=request.user_id,
            session_id=request.session_id,
            emitter=emitter,
            temporal_client=_get_temporal_client(),
            request_context=request.context,
            fs_tools_backend=get_fs_tools_backend(),
            request_id=request_id,
            parent_otel_context=parent_otel_context,
        ),
        name=f"agent-loop-{task_id}",
    )
    _running_tasks[task_id] = (None, loop_task)

    # loop_task 完成（正常或被取消）后确保 queue 有 sentinel，
    # 否则 SSE generator 会永远阻塞在 queue.get()
    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    async def generate() -> object:
        saw_request_end: bool = False
        try:
            start_event = EventModel(
                session_id=request.session_id,
                request_id=request_id,
                type=EventType.CHAT_REQUEST_START,
                data={"task_id": task_id},
            )
            yield f"event: {start_event.type.value}\ndata: {start_event.to_json()}\n\n"
            while True:
                event: EventModel | None = await queue.get()
                if event is None:
                    break
                if event.type == EventType.CHAT_REQUEST_END:
                    saw_request_end = True
                yield f"event: {event.type.value}\ndata: {event.to_json()}\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            _running_tasks.pop(task_id, None)
            if not loop_task.done():
                try:
                    if saw_request_end:
                        await asyncio.shield(loop_task)
                    else:
                        loop_task.cancel()
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


@app.post("/chat/sync")
async def chat_sync(request: ChatRequest, raw_request: Request) -> JSONResponse:
    """同步对话接口（非 SSE）。

    等待 Agent 执行完成后返回 JSON 结果，适合测试和外部集成。

    返回格式：
        {
            "session_id": "...",
            "text": "Agent 最终回复文本",
            "tool_calls": [{"tool_name": "...", "tool_call_id": "..."}],
            "tool_results": [{"tool_name": "...", "result": "..."}],
            "finish_reason": "end_turn" | "error" | ...,
            "error": null | "错误信息"
        }
    """
    from agent_sdk._event.event_emitter import EventEmitter
    from agent_sdk._event.event_model import EventModel
    from agent_sdk._event.event_type import EventType
    from agent_sdk._config.settings import get_fs_tools_backend

    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter: EventEmitter = EventEmitter(queue)

    agent = _get_agent()
    request_id, parent_otel_context = _resolve_trace_context(raw_request)
    task_id: str = f"{request.session_id}-sync-{id(request)}"

    loop_task: asyncio.Task[None] = asyncio.create_task(
        agent.run(
            message=request.message,
            user_id=request.user_id,
            session_id=request.session_id,
            emitter=emitter,
            temporal_client=_get_temporal_client(),
            request_context=request.context,
            fs_tools_backend=get_fs_tools_backend(),
            request_id=request_id,
            parent_otel_context=parent_otel_context,
        ),
        name=f"agent-loop-{task_id}",
    )
    _running_tasks[task_id] = (None, loop_task)

    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    text_parts: list[str] = []
    finish_reason: str | None = None
    error: str | None = None

    try:
        while True:
            event: EventModel | None = await queue.get()
            if event is None:
                break
            if event.type == EventType.TEXT:
                content: str = event.data.get("content", "")
                if content:
                    text_parts.append(content)
            elif event.type == EventType.ERROR:
                error = event.data.get("message", event.data.get("error", str(event.data)))
            elif event.type == EventType.CHAT_REQUEST_END:
                finish_reason = event.finish_reason
    finally:
        _running_tasks.pop(task_id, None)

    return JSONResponse(content={
        "session_id": request.session_id,
        "text": "".join(text_parts),
        "finish_reason": finish_reason,
        "error": error,
    })


@app.post("/chat/stop")
async def chat_stop(request: StopRequest) -> JSONResponse:
    """停止正在运行的对话任务。"""
    entry = _running_tasks.get(request.task_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "任务不存在或已结束"})

    task_obj, loop_task = entry
    if task_obj is not None and hasattr(task_obj, "cancelled"):
        task_obj.cancelled = True  # type: ignore[union-attr]
    if not loop_task.done():
        loop_task.cancel()

    return JSONResponse({"status": "cancelled", "task_id": request.task_id})


@app.post("/chat/interrupt-reply")
async def interrupt_reply(request: InterruptReplyRequest) -> JSONResponse:
    """回复一个等待中的 interrupt，恢复 agent 执行。

    前端收到 interrupt 事件后，用户操作完毕调用此接口。
    interrupt_key 来自 interrupt 事件的 data.interrupt_key 字段。
    支持 Temporal 模式和内存模式（TEMPORAL_ENABLED=false）。
    """
    from agent_sdk._agent.interrupt import is_interrupt_active, resume

    reply_data = request.reply if isinstance(request.reply, dict) else {"reply": request.reply}

    # 检查 interrupt 是否在当前进程中活跃
    # 不活跃 = server 重启过，agent loop 已丢失
    if not is_interrupt_active(request.interrupt_key):
        # 仍然尝试完成 workflow（清理资源），但告知前端已失效
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
        # client=None 时 resume 走内存模式
        await resume(_temporal_client, request.interrupt_key, reply_data)
        return JSONResponse({"status": "ok", "interrupt_key": request.interrupt_key})
    except Exception as exc:
        logger.warning(f"interrupt-reply failed: {exc}")
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "interrupt_key": request.interrupt_key},
        )


@app.post("/chat/stream/async")
async def chat_stream_async(request: AsyncChatRequest, raw_request: Request) -> JSONResponse:
    """Orchestrator 编排模式入口：接受编排字段 + 在 try/finally 里兜底 callback。

    和 /chat/async 的区别：
    - 不强依赖 Kafka（没启用时也能跑，事件扔到 /dev/null）
    - 把 request 里的 workflow_id / current_step / step_skeleton 等透传进 Agent.run()
    - 在 try/finally 里调 callback_url 通知 orchestrator turn 结束（design.md §8.1）

    降级时 ChatManager 不应调这个接口，走 /chat/stream 或 /chat/async。
    """
    import time as _time
    from agent_sdk._config.settings import get_kafka_config
    from agent_sdk._event.event_emitter import EventEmitter
    from agent_sdk._event.event_model import EventModel
    from agent_sdk._event.event_sinker_kafka import KafkaSinker, get_kafka_producer

    agent = _get_agent()
    request_id: str = request.request_id or _resolve_trace_context(raw_request)[0]
    _, parent_otel_context = _resolve_trace_context(raw_request)
    task_id: str = f"{request.session_id}-orch-{request_id[:8]}"

    # 事件队列 + sinker：Kafka 启用就走 Kafka，没启用就丢弃（orchestrator 不消费）
    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter = EventEmitter(queue)
    kafka_config = get_kafka_config()

    async def _drain_queue() -> None:
        """Kafka 未启用时的 no-op drain：只把 queue 清空避免内存泄漏"""
        while True:
            event = await queue.get()
            if event is None:
                break

    async def _forward_to_kafka() -> None:
        """Kafka 启用时的正常转发"""
        try:
            producer = await get_kafka_producer()
            sinker = KafkaSinker(producer, kafka_config.topic)
            while True:
                event = await queue.get()
                if event is None:
                    break
                await sinker.send(event)
        except Exception:
            logger.exception("Kafka 转发异常")

    _callback_url: str = request.callback_url or ""

    async def _run_with_callback() -> None:
        """try/finally 兜底：任何出口都调 callback_url 通知 orchestrator"""
        err_msg: str | None = None
        status: str = "success"
        try:
            await agent.run(
                message=request.message,
                user_id=request.user_id,
                session_id=request.session_id,
                emitter=emitter,
                temporal_client=_get_temporal_client(),
                request_context=request.context,
                request_id=request_id,
                parent_otel_context=parent_otel_context,
                # orchestrator 编排字段在 request_context.orchestrator 里，
                # 由 StageHook 从 deps.request_context 解包到 deps 各字段
            )
        except asyncio.CancelledError:
            status = "stopped"
            raise
        except Exception as e:  # noqa: BLE001
            status = "failure"
            err_msg = str(e)
            logger.exception(f"agent run failed: {request_id}")
        finally:
            queue.put_nowait(None)
            _running_tasks.pop(task_id, None)
            if _callback_url:
                import httpx as _httpx
                try:
                    async with _httpx.AsyncClient(timeout=5.0) as cli:
                        await asyncio.shield(cli.post(
                            _callback_url,
                            json={
                                "request_id": request_id,
                                "status": status,
                                "error_message": err_msg,
                                "completed_at": int(_time.time()),
                            },
                        ))
                except Exception:
                    logger.exception(f"callback failed: {_callback_url}")

    # 启动 agent 和事件 drain
    loop_task = asyncio.create_task(_run_with_callback(), name=f"orch-loop-{task_id}")
    _running_tasks[task_id] = (None, loop_task)

    if kafka_config.enabled:
        asyncio.create_task(_forward_to_kafka(), name=f"orch-kafka-{task_id}")
    else:
        asyncio.create_task(_drain_queue(), name=f"orch-drain-{task_id}")

    return JSONResponse({
        "status": "accepted",
        "task_id": task_id,
        "request_id": request_id,
    })


@app.post("/chat/async")
async def chat_async(request: AsyncChatRequest, raw_request: Request) -> JSONResponse:
    """异步对话接口：立即返回 task_id，事件通过 Kafka 推送。

    需要 KAFKA_ENABLED=true 才可用。
    """
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

    producer = await get_kafka_producer()
    sinker = KafkaSinker(producer, kafka_config.topic)

    queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
    emitter = EventEmitter(queue)

    agent = _get_agent()
    request_id, parent_otel_context = _resolve_trace_context(raw_request)
    task_id: str = f"{request.session_id}-async-{id(request)}"

    loop_task = asyncio.create_task(
        agent.run(
            message=request.message,
            user_id=request.user_id,
            session_id=request.session_id,
            emitter=emitter,
            temporal_client=_get_temporal_client(),
            request_context=request.context,
            request_id=request_id,
            parent_otel_context=parent_otel_context,
        ),
        name=f"agent-loop-async-{task_id}",
    )
    _running_tasks[task_id] = (None, loop_task)

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
            _running_tasks.pop(task_id, None)

    asyncio.create_task(
        _forward_to_kafka(),
        name=f"kafka-forward-{task_id}",
    )

    # loop_task 完成后确保 queue 有 sentinel
    def _ensure_sentinel(fut: asyncio.Task[None]) -> None:
        queue.put_nowait(None)

    loop_task.add_done_callback(_ensure_sentinel)

    return JSONResponse({"status": "accepted", "task_id": task_id})


# SPA 路由回退（必须在所有 API 路由之后注册，否则会拦截 POST 请求）
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

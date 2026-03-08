"""FastAPI 应用"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from src.server.request import ChatRequest
from src.server.skill_api import router as skill_router

logger: logging.Logger = logging.getLogger(__name__)

app: FastAPI = FastAPI(
    title="ChatAgent API",
    description="通用对话 Agent",
    version="0.1.0",
)

# CORS（允许 Vite dev server 跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Skill 管理 API
app.include_router(skill_router)

_WEB_DIR: Path = Path(__file__).parent.parent.parent / "web"


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查"""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """测试 UI 主页"""
    html_file = _WEB_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
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
    from src.agent.deps import AgentDeps
    from src.agent.loop import create_agent, run_agent_loop
    from src.agent.model import create_model
    from src.agent.tools import ALL_FS_TOOLS, create_default_tool_map
    from src.common.session_request_task import SessionRequestTask
    from src.event.event_emitter import EventEmitter
    from src.event.event_model import EventModel
    from src.event.event_sinker_sse import SseSinker

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
    )

    model = create_model()
    agent = create_agent(model)
    deps: AgentDeps = AgentDeps(
        session_id=request.session_id,
        user_id=request.user_id,
        available_tools=list(ALL_FS_TOOLS),
        tool_map=create_default_tool_map(),
    )

    # 后台运行 Agent Loop，前台 SSE generator 消费事件
    loop_task: asyncio.Task[None] = asyncio.create_task(
        run_agent_loop(emitter, task, agent, deps),
        name=f"agent-loop-{task.task_id}",
    )

    async def generate() -> object:
        try:
            while True:
                event: EventModel | None = await queue.get()
                if event is None:
                    break
                yield f"event: {event.type.value}\ndata: {event.to_json()}\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            task.cancelled = True
        finally:
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

"""FastAPI 应用"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.server.request import ChatRequest

app: FastAPI = FastAPI(
    title="ChatAgent API",
    description="通用对话 Agent",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查"""
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    """对话接口（占位，后续改为 SSE 流式）"""
    return JSONResponse(content={
        "session_id": request.session_id,
        "message": "Agent 尚未接入",
    })

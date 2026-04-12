"""/classify 路由。独立文件，**不用 from __future__ import annotations**。

FastAPI 需要真实的 type annotation（不是字符串）来解析 body 参数。
mainagent/src/app.py 有 `from __future__ import annotations` 导致所有
annotation 变成字符串，FastAPI 会把 body 参数当 query 解析 → 422。
"""

from fastapi import APIRouter
from src.classify import ClassifyRequest, ClassifyResponse, classify_scenario

router = APIRouter()

# agent 实例由 app.py 注入
_memory_service_factory = None


def set_memory_factory(factory) -> None:
    global _memory_service_factory
    _memory_service_factory = factory


@router.post("/classify")
async def classify_endpoint(req: ClassifyRequest) -> ClassifyResponse:
    scenario = await classify_scenario(
        user_id=req.user_id,
        session_id=req.session_id,
        message=req.message,
        memory_service_factory=_memory_service_factory,
    )
    return ClassifyResponse(scenario=scenario)

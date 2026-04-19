"""/plan 路由。独立文件，**不用 from __future__ import annotations**。

FastAPI 需要真实的 type annotation（不是字符串）来解析 body 参数 ——
否则 body 会被当成 query 参数导致 422。同 src/classify_router.py。

请求体里 context 必须带：
- scenes: list[str]（BMA 返回的场景列表，决定 plan prompts 目录；长度 1=单场景，>=2=复合场景）
- available_actions: [{name, desc}]（规划器白名单，由 orchestrator 现场传入）
"""

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_ai.exceptions import UnexpectedModelBehavior

from src.dsl_models import ActionDef, Plan
from src.plan import generate_plan
from src.plan_loader import PlanSceneNotFoundError

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter()

# memory_service 工厂由 app.py 注入（与 classify_router 同款模式）
_memory_service_factory: Any = None


def set_memory_factory(factory: Any) -> None:
    global _memory_service_factory
    _memory_service_factory = factory


class PlanContext(BaseModel):
    """/plan 请求的 context 字段强类型。"""

    model_config = {"extra": "allow"}

    scenes: list[str]
    """BMA 返回的场景列表；单场景就是长度 1，复合场景长度 >= 2。"""
    available_actions: list[ActionDef] = []


class PlanRequest(BaseModel):
    """/plan 请求体。"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    request_id: str | None = None
    context: PlanContext


@router.post("/plan")
async def plan_endpoint(req: PlanRequest) -> JSONResponse:
    """同步生成 DSL 规划。

    成功：HTTP 200 + Plan JSON
    scenes 为空 / 场景 prompts 不存在：HTTP 400
    LLM 多次 retry 仍校验失败：HTTP 500
    其他未预期异常：HTTP 500
    """
    if not req.context.scenes:
        return JSONResponse(
            status_code=400,
            content={"error": "scenes_empty", "detail": "context.scenes 不能为空"},
        )
    try:
        plan: Plan = await generate_plan(
            user_id=req.user_id,
            session_id=req.session_id,
            message=req.message,
            scenes=req.context.scenes,
            available_actions=req.context.available_actions,
            memory_service_factory=_memory_service_factory,
        )
    except PlanSceneNotFoundError as exc:
        logger.warning("[/plan] 场景未配置: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": "scene_not_configured", "detail": str(exc)},
        )
    except UnexpectedModelBehavior as exc:
        logger.error("[/plan] pydantic-ai 多次 retry 仍校验失败: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "invalid_plan_output", "detail": str(exc)},
        )
    except Exception as exc:
        logger.exception("[/plan] 未预期异常")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": f"{type(exc).__name__}: {exc}"},
        )

    return JSONResponse(status_code=200, content=plan.model_dump())

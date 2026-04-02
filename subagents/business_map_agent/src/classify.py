"""场景分类端点：调小模型判断用户意图所属场景。

POST /classify
请求：{ message, recent_turns? }
响应：{ scenes: ["platform"] } 或 { scenes: ["platform", "searchshops"] } 或 { scenes: [] }

BMA 只做场景分类，不决定 tools/skills。
MainAgent hook 根据分类结果加载对应场景配置。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logger: logging.Logger = logging.getLogger(__name__)

# 合法场景 id 列表
VALID_SCENES: list[str] = ["platform", "searchshops", "searchcoupons", "insurance"]


# ============================================================
# 请求 / 响应模型
# ============================================================


class RecentTurn(BaseModel):
    """最近一轮对话。"""

    role: str       # "user" | "assistant"
    content: str


class ClassifyRequest(BaseModel):
    """场景分类请求。"""

    message: str
    recent_turns: list[RecentTurn] = []


class ClassifyResponse(BaseModel):
    """场景分类响应：返回匹配的场景列表。"""

    scenes: list[str]


# ============================================================
# System Prompt 加载
# ============================================================

_SYSTEM_PROMPT: str = ""


def _load_system_prompt() -> str:
    """从 prompts/system.md 加载系统提示词（懒加载）。"""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT:
        return _SYSTEM_PROMPT
    prompt_path: Path = Path(__file__).resolve().parent.parent / "prompts" / "SYSTEM.md"
    if prompt_path.exists():
        _SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip()
    else:
        logger.warning("SYSTEM.md 不存在: %s", prompt_path)
        _SYSTEM_PROMPT = "你是场景分类器。严格输出 JSON 对象，格式为 {\"scenes\": [...]}。"
    return _SYSTEM_PROMPT


# ============================================================
# LLM 直调（Azure OpenAI）
# ============================================================


async def _call_llm(
    message: str,
    recent_turns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """调小模型进行场景分类。支持 Azure OpenAI 和 OpenAI-compatible API（如 DashScope）。"""
    # 优先 Azure OpenAI，其次 OpenAI-compatible（DashScope 等）
    azure_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    openai_endpoint: str = os.getenv("BMA_LLM_ENDPOINT", "")
    openai_key: str = os.getenv("BMA_LLM_API_KEY", "")
    openai_model: str = os.getenv("BMA_LLM_MODEL", "qwen3-30b-a3b")

    use_azure: bool = bool(azure_endpoint and azure_key)
    use_openai_compat: bool = bool(openai_endpoint and openai_key)

    if not use_azure and not use_openai_compat:
        logger.warning("LLM 未配置（Azure/OpenAI-compatible 均无），返回空场景列表")
        return {"scenes": []}

    if use_azure:
        deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4.1-mini")
        api_version: str = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
        url: str = (
            f"{azure_endpoint.rstrip('/')}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )
        headers: dict[str, str] = {"api-key": azure_key, "Content-Type": "application/json"}
    else:
        url = f"{openai_endpoint.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}

    system_prompt: str = _load_system_prompt()

    # 对话历史
    history_text: str = "（无）"
    if recent_turns:
        history_lines: list[str] = [
            f"{t['role']}: {t['content']}" for t in recent_turns
        ]
        history_text = "\n".join(history_lines)

    user_prompt: str = (
        f"[最近对话]\n{history_text}\n\n"
        f"[用户消息]\n{message}"
    )

    request_body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if not use_azure:
        request_body["model"] = openai_model
        request_body["enable_thinking"] = False

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp: httpx.Response = await client.post(url, headers=headers, json=request_body)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        content: str = data["choices"][0]["message"]["content"]
        return json.loads(content)


# ============================================================
# /classify 端点
# ============================================================


async def _do_classify(request: ClassifyRequest) -> ClassifyResponse:
    """场景分类。"""
    scenes: list[str] = []

    turns: list[dict[str, str]] = (
        [{"role": t.role, "content": t.content} for t in request.recent_turns]
        if request.recent_turns
        else []
    )
    logger.info("BMA classify: message='%s', recent_turns=%d条", request.message, len(turns))
    if turns:
        logger.info("BMA recent_turns: %s", turns[-4:])

    try:
        llm_result: dict[str, Any] = await _call_llm(
            request.message, recent_turns=turns
        )
        raw_scenes: list[str] = llm_result.get("scenes", [])
        scenes = [s for s in raw_scenes if s in VALID_SCENES]
    except Exception:
        logger.warning("LLM 场景分类失败", exc_info=True)

    logger.info("场景分类结果: %s", scenes)
    return ClassifyResponse(scenes=scenes)


# ============================================================
# FastAPI 应用
# ============================================================


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    from fastapi.middleware.cors import CORSMiddleware

    # 配置日志输出到文件
    log_dir: Path = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler: logging.FileHandler = logging.FileHandler(log_dir / "bma.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)

    app: FastAPI = FastAPI(
        title="BusinessMapAgent",
        description="场景分类服务",
        version="4.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "business_map_agent"}

    @app.post("/classify", response_model=ClassifyResponse)
    async def classify(request: ClassifyRequest) -> ClassifyResponse:
        """场景分类端点。"""
        return await _do_classify(request)

    return app

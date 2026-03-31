"""意图因子提取端点：调小模型提取用户意图因子。

POST /classify
请求：{ message, recent_turns? }
响应：{ factors: { "intent.xxx": value, ... } }

BMA 只做意图提取，不决定 tools/skills。
阶段判断（S1/S2）由 MainAgent hook 负责。
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


# ============================================================
# 请求 / 响应模型
# ============================================================


class RecentTurn(BaseModel):
    """最近一轮对话。"""

    role: str       # "user" | "assistant"
    content: str


class ClassifyRequest(BaseModel):
    """意图因子提取请求。"""

    message: str
    recent_turns: list[RecentTurn] = []


class ClassifyResponse(BaseModel):
    """意图因子提取响应：只返回因子值。"""

    factors: dict[str, Any]


# ============================================================
# 因子定义加载（从 scene_config.yaml）
# ============================================================

_factor_defs_text: str = ""
_factor_names: list[str] = []


def _ensure_factor_defs() -> None:
    """加载 scene_config.yaml 中的因子定义。"""
    global _factor_defs_text, _factor_names
    if _factor_defs_text:
        return

    import yaml

    config_path_str: str = os.getenv("SCENE_CONFIG_PATH", "")
    if config_path_str:
        config_path: Path = Path(config_path_str)
    else:
        config_path = (
            Path(__file__).resolve().parents[3]
            / "extensions"
            / "business-map"
            / "scene_config.yaml"
        )

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    factors_raw: dict[str, Any] = raw.get("factors", {})

    lines: list[str] = []
    names: list[str] = []

    item: dict[str, Any]
    for item in factors_raw.get("bool", []):
        names.append(item["name"])
        lines.append(f"- {item['name']} (bool): {item['description']}")

    for item in factors_raw.get("enum", []):
        names.append(item["name"])
        options: str = " / ".join(item["options"])
        lines.append(f"- {item['name']} (enum: {options}): {item['description']}")

    _factor_defs_text = "\n".join(lines)
    _factor_names = names

    logger.info("加载 %d 个因子定义", len(names))


# ============================================================
# System Prompt 加载
# ============================================================

_SYSTEM_PROMPT: str = ""


def _load_system_prompt() -> str:
    """从 prompts/system.md 加载系统提示词（懒加载）。"""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT:
        return _SYSTEM_PROMPT
    prompt_path: Path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
    if prompt_path.exists():
        _SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip()
    else:
        logger.warning("system.md 不存在: %s", prompt_path)
        _SYSTEM_PROMPT = "你是意图标签提取器。严格输出 JSON 对象。"
    return _SYSTEM_PROMPT


# ============================================================
# LLM 直调（Azure OpenAI）
# ============================================================


async def _call_llm(
    message: str,
    factor_defs: str,
    recent_turns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """调小模型提取意图因子。"""
    endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4.1-mini")
    api_version: str = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")

    if not endpoint or not api_key:
        logger.warning("Azure OpenAI 未配置，返回空因子")
        return {}

    url: str = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )

    system_prompt: str = _load_system_prompt()

    # 对话历史
    history_text: str = "（无）"
    if recent_turns:
        history_lines: list[str] = [
            f"{t['role']}: {t['content']}" for t in recent_turns
        ]
        history_text = "\n".join(history_lines)

    user_prompt: str = (
        f"[标签定义]\n{factor_defs}\n\n"
        f"[最近对话]\n{history_text}\n\n"
        f"[用户消息]\n{message}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp: httpx.Response = await client.post(
            url,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        content: str = data["choices"][0]["message"]["content"]
        return json.loads(content)


# ============================================================
# /classify 端点
# ============================================================


async def _do_classify(request: ClassifyRequest) -> ClassifyResponse:
    """提取意图因子。"""
    _ensure_factor_defs()

    factors: dict[str, Any] = {}

    if _factor_names:
        turns: list[dict[str, str]] = (
            [{"role": t.role, "content": t.content} for t in request.recent_turns]
            if request.recent_turns
            else []
        )
        try:
            llm_result: dict[str, Any] = await _call_llm(
                request.message, _factor_defs_text, recent_turns=turns
            )
            # 只保留声明过的因子
            name: str
            for name in _factor_names:
                if name in llm_result:
                    factors[name] = llm_result[name]
        except Exception:
            logger.warning("LLM 意图提取失败", exc_info=True)

    logger.info("意图因子提取: %s", factors)

    return ClassifyResponse(factors=factors)


# ============================================================
# FastAPI 应用
# ============================================================


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    from fastapi.middleware.cors import CORSMiddleware

    app: FastAPI = FastAPI(
        title="BusinessMapAgent",
        description="意图因子提取服务",
        version="3.0",
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
        """意图因子提取端点。"""
        return await _do_classify(request)

    return app

"""场景分类端点：调小模型判断用户意图所属场景与阶段。

POST /classify
请求：{ message, recent_turns? }
响应：
  {
    "scenes": [
      {"name": "searchcoupons", "phase": "followup"},
      {"name": "searchshops", "phase": "intake"}
    ]
  }

BMA 只做场景与阶段分类，不决定 tools/skills。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logger: logging.Logger = logging.getLogger(__name__)

# 合法场景 / 阶段 id 列表
VALID_SCENES: list[str] = ["guide", "searchshops", "searchcoupons"]
VALID_PHASES: list[str] = ["intake", "followup"]


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


class ScenePhase(BaseModel):
    """单个场景的阶段判断结果。"""

    name: str
    phase: str


class ClassifyResponse(BaseModel):
    """场景分类响应：返回匹配的场景与阶段列表。"""

    scenes: list[ScenePhase]


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
    use_multi_turn: bool = False,
) -> dict[str, Any]:
    """调小模型进行场景分类。支持 Azure OpenAI 和 OpenAI-compatible API（如 DashScope）。

    Args:
        message: 用户当前消息
        recent_turns: 最近对话历史
        use_multi_turn: False=方案A（历史拼入user prompt），True=方案B（历史作为独立message）
    """
    # 优先 Azure OpenAI，其次 OpenAI-compatible（DashScope 等）
    azure_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    openai_endpoint: str = os.getenv("BMA_LLM_ENDPOINT", "")
    openai_key: str = os.getenv("BMA_LLM_API_KEY", "")
    openai_model: str = os.getenv("BMA_LLM_MODEL", "qwen3-30b-a3b")

    use_azure: bool = bool(azure_endpoint and azure_key)
    use_openai_compat: bool = bool(openai_endpoint and openai_key)

    if not use_azure and not use_openai_compat:
        logger.warning("LLM 未配置（Azure/OpenAI-compatible 均无），返回 guide/intake")
        return {"scenes": [{"name": "guide", "phase": "intake"}]}

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

    if use_multi_turn:
        # 方案 B：recent_turns 作为独立 message 对象
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if recent_turns:
            for turn in recent_turns:
                role: str = turn["role"]
                content: str = turn["content"]
                # 截断过长的 assistant 回复（去掉 spec 块，只保留文本）
                if role == "assistant" and len(content) > 200:
                    content = re.sub(r'```spec\n.*?```', '[优惠卡片数据]', content, flags=re.DOTALL)
                    if len(content) > 200:
                        content = content[:200] + "..."
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
    else:
        # 方案 A：历史拼入 user prompt
        history_text: str = "（无）"
        if recent_turns:
            history_lines: list[str] = []
            for t in recent_turns:
                role_label: str = "[User]" if t["role"] == "user" else "[Assistant]"
                content: str = t["content"]
                # assistant 回复截断：spec 卡片替换为 [卡片]，超长截断
                if t["role"] == "assistant":
                    content = re.sub(r'```spec\n.*?```', '[卡片]', content, flags=re.DOTALL)
                    content = re.sub(r'```action\n.*?```', '[操作]', content, flags=re.DOTALL)
                    if len(content) > 100:
                        content = content[:100] + "..."
                history_lines.append(f"{role_label} {content}")
            history_text = "\n".join(history_lines)

        user_prompt: str = (
            f"Recent (last {len(recent_turns) if recent_turns else 0}):\n{history_text}\n\n"
            f"Current:\n[User] {message}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    request_body: dict[str, Any] = {
        "messages": messages,
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
        raw_content: str = data["choices"][0]["message"]["content"]
        return json.loads(raw_content)


# ============================================================
# /classify 端点
# ============================================================


async def _do_classify(
    request: ClassifyRequest,
    use_multi_turn: bool = False,
) -> ClassifyResponse:
    """场景与阶段分类。

    Args:
        request: 分类请求
        use_multi_turn: False=方案A，True=方案B（multi-turn messages）
    """
    scenes: list[ScenePhase] = []
    scheme_label: str = "B" if use_multi_turn else "A"

    turns: list[dict[str, str]] = (
        [{"role": t.role, "content": t.content} for t in request.recent_turns]
        if request.recent_turns
        else []
    )
    logger.info(
        "BMA classify(方案%s): message='%s', recent_turns=%d条",
        scheme_label, request.message, len(turns),
    )
    if turns:
        logger.info("BMA recent_turns: %s", turns[-4:])

    try:
        llm_result: dict[str, Any] = await _call_llm(
            request.message, recent_turns=turns, use_multi_turn=use_multi_turn,
        )
        raw_scenes: list[dict[str, Any]] = list(llm_result.get("scenes", []))
        seen: set[tuple[str, str]] = set()
        for item in raw_scenes:
            if not isinstance(item, dict):
                continue
            name: Any = item.get("name")
            phase: Any = item.get("phase")
            if not isinstance(name, str) or name not in VALID_SCENES:
                continue
            if not isinstance(phase, str) or phase not in VALID_PHASES:
                continue
            key: tuple[str, str] = (name, phase)
            if key in seen:
                continue
            seen.add(key)
            scenes.append(ScenePhase(name=name, phase=phase))
    except Exception:
        logger.warning("LLM 场景/阶段分类失败（方案%s）", scheme_label, exc_info=True)

    logger.info("场景分类结果（方案%s）: %s", scheme_label, scenes)
    if not scenes:
        scenes = [ScenePhase(name="guide", phase="intake")]
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
        """场景分类端点（方案 A：历史拼入 user prompt）。"""
        return await _do_classify(request, use_multi_turn=False)

    @app.post("/classify_b", response_model=ClassifyResponse)
    async def classify_b(request: ClassifyRequest) -> ClassifyResponse:
        """场景分类端点（方案 B：历史作为独立 multi-turn messages）。"""
        return await _do_classify(request, use_multi_turn=True)

    return app

"""场景分类端点：基于决策树的场景路由服务。

POST /classify
请求：{ message: str, slot_state: dict }
响应：{ scene_id, scene_name, goal, target_slots, tools, strategy, eval_path }

内部流程：
1. 加载 scene_config（SceneService 单例）
2. 构建 slot 因子
3. 关键词因子匹配
4. 决策树预扫描 → 收集需要的 BMA 因子
5. 如果需要 → 直接调 Azure OpenAI 判断意图标签
6. 走完决策树
7. 返回场景配置
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
    """场景分类请求。"""

    message: str
    slot_state: dict[str, str | None]
    recent_turns: list[RecentTurn] = []


class TargetSlotResponse(BaseModel):
    """目标槽位定义（响应用）。"""

    label: str
    required: str
    method: str
    condition: str | None = None


class ClassifyResponse(BaseModel):
    """场景分类响应。"""

    scene_id: str
    scene_name: str
    goal: str
    target_slots: dict[str, TargetSlotResponse]
    tools: list[str]
    skills: list[str]
    strategy: str
    eval_path: list[str]


# ============================================================
# SceneService 加载（模块级状态）
# ============================================================

_scene_service_loaded: bool = False


def _ensure_scene_service() -> None:
    """确保 SceneService 已加载 scene_config.yaml。"""
    global _scene_service_loaded
    if _scene_service_loaded:
        return

    from hlsc.services.scene_service import scene_service

    config_path: str = os.getenv("SCENE_CONFIG_PATH", "")
    if config_path:
        scene_service.load(Path(config_path))
    else:
        # 默认路径：src/classify.py → src/ → business_map_agent/ → subagents/ → 项目根
        #   parents[0]=src/, [1]=business_map_agent/, [2]=subagents/, [3]=项目根
        default_path: Path = (
            Path(__file__).resolve().parents[3]
            / "extensions"
            / "business-map"
            / "scene_config.yaml"
        )
        scene_service.load(default_path)

    _scene_service_loaded = True


# ============================================================
# System Prompt 加载
# ============================================================

_SYSTEM_PROMPT: str = ""


def _load_system_prompt() -> str:
    """从 prompts/System.md 加载系统提示词（懒加载，只读一次）。"""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT:
        return _SYSTEM_PROMPT
    prompt_path: Path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
    if prompt_path.exists():
        _SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip()
    else:
        logger.warning("System.md 不存在: %s，使用默认提示词", prompt_path)
        _SYSTEM_PROMPT = "你是意图标签提取器。严格输出 JSON 对象。"
    return _SYSTEM_PROMPT


# ============================================================
# LLM 直调（Azure OpenAI）
# ============================================================


async def _call_llm_for_factors(
    message: str,
    factor_defs: str,
    slot_summary: str,
    recent_turns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """直接调用 Azure OpenAI 获取意图标签。

    不经过 Agent SDK，使用 httpx 直调 Azure REST API，
    以 response_format: json_object 确保结构化输出。
    """
    endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4.1-mini")
    api_version: str = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")

    if not endpoint or not api_key:
        logger.warning("Azure OpenAI 未配置，跳过 LLM 调用")
        return {}

    url: str = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

    # 加载 System.md 提示词
    system_prompt: str = _load_system_prompt()

    # 构建最近对话文本
    history_text: str = "（无）"
    if recent_turns:
        history_lines: list[str] = []
        for turn in recent_turns:
            history_lines.append(f"{turn['role']}: {turn['content']}")
        history_text = "\n".join(history_lines)

    # 构建 user prompt
    user_prompt: str = (
        f"[标签定义]\n{factor_defs}\n\n"
        f"[已确认信息]\n{slot_summary}\n\n"
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
# 因子构建辅助
# ============================================================


def _build_factor_definitions(
    needed_factors: list[str],
    config: Any,
) -> str:
    """构建需要 LLM 判断的因子定义文本。"""
    lines: list[str] = []
    factor_name: str
    for factor_name in needed_factors:
        # 查找 bool 因子
        for bf in config.factors.bma_bool_factors:
            if bf.name == factor_name:
                lines.append(f"- {factor_name} (bool): {bf.description}")
                break
        # 查找 enum 因子
        for ef in config.factors.bma_enum_factors:
            if ef.name == factor_name:
                options: str = " / ".join(ef.options)
                lines.append(
                    f"- {factor_name} (enum: {options}): {ef.description}"
                )
                break
    return "\n".join(lines) if lines else ""


def _build_slot_summary(slots: dict[str, str | None]) -> str:
    """构建 slot 状态摘要文本。"""
    filled: dict[str, str] = {k: v for k, v in slots.items() if v is not None}
    if not filled:
        return "（无）"
    return "\n".join(f"  {k} = {v}" for k, v in filled.items())


def _parse_llm_response(
    raw: dict[str, Any],
    needed_factors: list[str],
) -> dict[str, str | bool | None]:
    """从 LLM JSON 响应中提取所需因子值。"""
    result: dict[str, str | bool | None] = {}
    factor: str
    for factor in needed_factors:
        if factor in raw:
            result[factor] = raw[factor]
    return result


# ============================================================
# /classify 端点实现
# ============================================================


async def _do_classify(request: ClassifyRequest) -> ClassifyResponse:
    """场景分类核心逻辑。"""
    _ensure_scene_service()

    from hlsc.services.decision_tree_evaluator import (
        FactorValues,
        TreeEvalResult,
        collect_bma_factors_needed,
        evaluate_keyword_factors,
        evaluate_tree,
    )
    from hlsc.services.scene_service import SceneConfig, SceneServiceConfig, scene_service

    config: SceneServiceConfig = scene_service.config

    # 1. 构建 slot 因子
    factors: FactorValues = {}
    slot_factor: str
    for slot_factor in config.factors.slot_factors:
        short_name: str = slot_factor.replace("slot.", "")
        factors[slot_factor] = request.slot_state.get(short_name)

    # 2. 关键词因子匹配
    kw_results: dict[str, bool] = evaluate_keyword_factors(
        request.message, config.factors.keyword_factors
    )
    factors.update(kw_results)

    # 3. 决策树预扫描，收集需要的 BMA 因子
    needed_bma: list[str] = collect_bma_factors_needed(config.tree, factors)

    # 4. 如果需要 BMA 因子 → 直接调 Azure OpenAI
    if needed_bma:
        factor_defs: str = _build_factor_definitions(needed_bma, config)
        slot_summary: str = _build_slot_summary(request.slot_state)
        try:
            # 转换 recent_turns 为 dict 列表
            turns: list[dict[str, str]] = [
                {"role": t.role, "content": t.content} for t in request.recent_turns
            ] if request.recent_turns else []
            llm_result: dict[str, Any] = await _call_llm_for_factors(
                request.message, factor_defs, slot_summary, recent_turns=turns
            )
            bma_values: dict[str, str | bool | None] = _parse_llm_response(
                llm_result, needed_bma
            )
            factors.update(bma_values)
        except Exception:
            logger.warning("LLM 意图标签提取失败", exc_info=True)

    # 5. 走完决策树
    result: TreeEvalResult = evaluate_tree(config.tree, factors)
    scene: SceneConfig = scene_service.get_scene(result.scene_id)

    logger.info(
        "场景分类完成: scene=%s, path=%s",
        result.scene_id,
        result.path,
    )

    # 6. 构建响应（将 TargetSlot dataclass 转为 dict）
    target_slots_resp: dict[str, TargetSlotResponse] = {}
    slot_name: str
    for slot_name, ts in scene.target_slots.items():
        target_slots_resp[slot_name] = TargetSlotResponse(
            label=ts.label,
            required=ts.required,
            method=ts.method,
            condition=ts.condition,
        )

    return ClassifyResponse(
        scene_id=result.scene_id,
        scene_name=scene.name,
        goal=scene.goal,
        target_slots=target_slots_resp,
        tools=scene.tools,
        skills=scene.skills,
        strategy=scene.strategy,
        eval_path=result.path,
    )


# ============================================================
# 路由挂载
# ============================================================


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    from fastapi.middleware.cors import CORSMiddleware

    app: FastAPI = FastAPI(
        title="BusinessMapAgent",
        description="场景分类服务 — 基于决策树的场景路由",
        version="2.0",
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
        """场景分类端点：接收用户消息和槽位状态，返回场景配置。"""
        return await _do_classify(request)

    return app

"""场景编排器：通过 BusinessAgent HTTP API 进行场景分类与工具过滤。

流程（轻量化）：
1. 读 SlotState（从文件）
2. 调 BusinessAgent POST /classify（HTTP）
3. 构建 SceneContext（tools/skills 已在配置中分离）
4. 设置 deps.allowed_skills
5. 更新 SlotState
"""

from __future__ import annotations

import contextvars
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# 使用 contextvars 实现 async-safe 的 session 隔离。
# 每个 asyncio Task 拥有独立的 session_id，不会跨请求泄漏。
_current_session_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bm_current_session", default="default"
)

logger: logging.Logger = logging.getLogger(__name__)

BUSINESS_MAP_AGENT_URL: str = os.getenv(
    "BUSINESS_MAP_AGENT_URL", "http://localhost:8103"
)
# 传给 /classify 的最近对话轮数（每轮 = 一对 user+assistant）
CLASSIFY_RECENT_TURNS: int = int(os.getenv("CLASSIFY_RECENT_TURNS", "3"))


@dataclass
class SceneContext:
    """场景上下文，供 formatter 注入 LLM。"""

    scene_id: str
    scene_name: str
    goal: str
    target_slots: dict[str, Any]
    tools: list[str]
    allowed_skills: list[str]
    strategy: str
    slot_state: Any  # SlotState（延迟 import 避免顶层循环依赖）
    eval_path: list[str] = field(default_factory=list)


class SceneOrchestrator:
    """基于 HTTP API 的场景编排器（轻量版）。

    所有决策树逻辑已移至 BusinessAgent /classify 端点，
    本类只负责调 HTTP → 构建上下文 → 过滤工具 → 持久化。
    """

    def __init__(self) -> None:
        self._scene_contexts: dict[str, SceneContext] = {}

    # ------------------------------------------------------------------
    # 属性与查询
    # ------------------------------------------------------------------

    @property
    def current_session_id(self) -> str:
        """当前 async task 的 session_id（从 contextvars 读取，async-safe）。"""
        return _current_session_var.get()

    def get_scene_context(self, session_id: str) -> SceneContext | None:
        """获取指定 session 的场景上下文（供 formatter 使用）。"""
        return self._scene_contexts.get(session_id)

    # ------------------------------------------------------------------
    # BeforeAgentRunHook 主入口
    # ------------------------------------------------------------------

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: Any,
        message: str,
    ) -> None:
        """BeforeAgentRunHook 实现：调用 BusinessAgent /classify 进行场景编排。"""
        _current_session_var.set(session_id)

        from hlsc.services.slot_state_service import SlotState, slot_state_service

        inner_dir: str = os.getenv("INNER_STORAGE_DIR", "data/inner")
        session_dir: Path = Path(inner_dir) / user_id / "sessions" / session_id

        # 1. 读 SlotState
        slot_state: SlotState | None = slot_state_service.read(session_dir)
        slot_dict: dict[str, str | None] = slot_state.slots if slot_state else {}

        # 2. 截取最近对话历史
        recent_turns: list[dict[str, str]] = self._get_recent_turns(
            deps, CLASSIFY_RECENT_TURNS
        )

        # 3. 调 BusinessAgent HTTP API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp: httpx.Response = await client.post(
                    f"{BUSINESS_MAP_AGENT_URL}/classify",
                    json={
                        "message": message,
                        "slot_state": slot_dict,
                        "recent_turns": recent_turns,
                    },
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
        except Exception:
            logger.warning("BusinessAgent /classify 调用失败", exc_info=True)
            return

        # 4. 构建 SceneContext（tools 和 skills 已在配置中分离）
        scene_context: SceneContext = SceneContext(
            scene_id=result["scene_id"],
            scene_name=result["scene_name"],
            goal=result["goal"],
            target_slots=result["target_slots"],
            tools=result["tools"],
            allowed_skills=result.get("skills", []),
            strategy=result["strategy"],
            slot_state=slot_state or SlotState(slots=slot_dict),
            eval_path=result.get("eval_path", []),
        )
        self._scene_contexts[session_id] = scene_context

        logger.info(
            "场景定位: session=%s, scene=%s, skills=%s, path=%s",
            session_id,
            result["scene_id"],
            scene_context.allowed_skills,
            result.get("eval_path", []),
        )

        # 5. 设置 deps.allowed_skills（控制 skill listing 过滤）
        deps.allowed_skills = scene_context.allowed_skills if scene_context.allowed_skills else None

        # 6. 更新 SlotState
        if slot_state is None:
            slot_state = SlotState(slots=slot_dict)
        slot_state.current_scene = result["scene_id"]
        slot_state_service.write(session_dir, slot_state)

        logger.info(
            "allowed_skills=%s, tools=%s",
            scene_context.allowed_skills, scene_context.tools,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_recent_turns(deps: Any, max_turns: int) -> list[dict[str, str]]:
        """从 deps 的内存/存储中截取最近几轮对话。

        每轮 = 一对 user + assistant 消息。
        返回 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        turns: list[dict[str, str]] = []
        try:
            # 尝试从 inner_storage_backend 读取 transcript
            backend: Any = deps.inner_storage_backend
            if backend is None:
                return turns
            import json
            transcript_path: str = "transcript.jsonl"
            content: str = backend.read(transcript_path)
            if not content:
                return turns
            lines: list[str] = content.strip().splitlines()
            # 从后往前取最近 max_turns 轮（每轮 2 条消息）
            for line in reversed(lines):
                try:
                    entry: dict[str, Any] = json.loads(line)
                    role: str = entry.get("role", "")
                    text: str = entry.get("content", "")
                    if role in ("user", "assistant") and text:
                        turns.append({"role": role, "content": text[:500]})
                        if len(turns) >= max_turns * 2:
                            break
                except (json.JSONDecodeError, Exception):
                    continue
            turns.reverse()
        except Exception:
            logger.debug("获取最近对话历史失败", exc_info=True)
        return turns


# 模块级单例
scene_orchestrator: SceneOrchestrator = SceneOrchestrator()

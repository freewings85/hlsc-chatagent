"""MainAgent 前置 Hook：BMA 每轮分类路由到 6 个平等场景。

路由逻辑：
- BMA 返回 [] → guide（引导，有查询工具，无 confirm_booking）
- BMA 返回 1 个场景 → 该场景
- BMA 返回多个场景 → orchestrator（delegate 协调子 agent）
- BMA 调用失败 → guide（容错）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from agent_sdk._agent.deps import AgentDeps


# ============================================================
# 对话历史提取（给 BMA 做分类用）
# ============================================================


def _extract_recent_turns(deps: AgentDeps, max_turns: int = 5) -> list[dict[str, str]]:
    """从 inner_storage_backend 加载最近几轮对话，格式化为 BMA 需要的 recent_turns。

    返回 [{"role": "user"|"assistant", "content": "..."}]，最多 max_turns 轮。
    加载失败时返回空列表（不影响分类，BMA 会退化为只看当前消息）。
    """
    try:
        backend = deps.inner_storage_backend
        if backend is None:
            return []

        import json

        # 读取 messages.jsonl（和 MemoryMessageService 同路径）
        messages_path: str = f"sessions/{deps.session_id}/messages.jsonl"
        raw: str = backend.read(messages_path)
        if not raw:
            return []

        turns: list[dict[str, str]] = []
        for line in raw.strip().split("\n"):
            if not line.strip():
                continue
            msg: dict[str, Any] = json.loads(line)
            role: str = msg.get("role", "")
            # 提取文本内容
            parts: list[dict[str, Any]] = msg.get("parts", [])
            content_parts: list[str] = []
            for part in parts:
                if isinstance(part, dict) and part.get("content"):
                    content_parts.append(str(part["content"]))
            content: str = " ".join(content_parts).strip()
            if role in ("user", "assistant") and content:
                turns.append({"role": role, "content": content})

        # 返回最近 max_turns 轮
        return turns[-max_turns * 2:]  # 每轮包含 user + assistant
    except Exception:
        logger.debug("提取 recent_turns 失败，BMA 将只使用当前消息", exc_info=True)
        return []

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 场景配置（从 stage_config.yaml 加载）
# ============================================================


class SceneConfig:
    """场景配置：prompt_parts + agent_md + tools + skills。"""

    def __init__(
        self,
        name: str,
        prompt_parts: list[str],
        agent_md: str,
        tools: list[str],
        skills: list[str],
    ) -> None:
        self.name: str = name
        self.prompt_parts: list[str] = prompt_parts
        self.agent_md: str = agent_md
        self.tools: list[str] = tools
        self.skills: list[str] = skills


class SceneConfigLoader:
    """加载 stage_config.yaml 中的扁平 scenes 结构。"""

    def __init__(self) -> None:
        self._scenes: dict[str, SceneConfig] = {}
        self._loaded: bool = False

    def ensure_loaded(self) -> None:
        """确保配置已加载。"""
        if self._loaded:
            return

        config_path_str: str = os.getenv("STAGE_CONFIG_PATH", "")
        if config_path_str:
            config_path: Path = Path(config_path_str)
        else:
            config_path = Path(__file__).resolve().parent.parent / "stage_config.yaml"

        raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        scene_id: str
        scene_data: dict[str, Any]
        for scene_id, scene_data in raw.get("scenes", {}).items():
            self._scenes[scene_id] = SceneConfig(
                name=scene_id,
                prompt_parts=scene_data.get("prompt_parts", []),
                agent_md=scene_data.get("agent_md", ""),
                tools=scene_data.get("tools", []),
                skills=scene_data.get("skills", []),
            )

        self._loaded = True
        logger.info("场景配置加载完成: %d 个场景", len(self._scenes))

    def get_scene(self, scene_id: str) -> SceneConfig:
        """获取场景配置。未匹配时回退到 guide。"""
        self.ensure_loaded()
        if scene_id in self._scenes:
            return self._scenes[scene_id]
        logger.warning("场景 '%s' 不存在，回退到 guide", scene_id)
        return self._scenes["guide"]


# 模块级单例
_config_loader: SceneConfigLoader = SceneConfigLoader()


# ============================================================
# BMA 场景分类调用
# ============================================================


async def _call_bma_classify(message: str, recent_turns: list[dict[str, str]] | None = None) -> list[str]:
    """调用 BMA /classify 接口进行场景分类。

    Args:
        message: 当前用户消息
        recent_turns: 最近几轮对话 [{"role": "user"|"assistant", "content": "..."}]
    """
    url: str = os.getenv("BMA_CLASSIFY_URL", "")
    if not url:
        # 回退到旧环境变量
        from src.config import BUSINESS_MAP_AGENT_URL
        url = f"{BUSINESS_MAP_AGENT_URL.rstrip('/')}/classify"

    payload: dict[str, Any] = {"message": message}
    if recent_turns:
        payload["recent_turns"] = recent_turns

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp: httpx.Response = await client.post(url, json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            scenes: list[str] = data.get("scenes", [])
            logger.info("BMA 场景分类: %s → %s", message[:50], scenes)
            return scenes
    except Exception:
        logger.warning("BMA 场景分类调用失败，回退到 guide", exc_info=True)
        return []


# ============================================================
# Hook 实现
# ============================================================


class StageHook:
    """MainAgent 前置 Hook：BMA 分类 → 场景路由 → 加载配置。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        _config_loader.ensure_loaded()

        # 提取最近几轮对话历史给 BMA
        recent_turns: list[dict[str, str]] = _extract_recent_turns(deps, max_turns=5)

        # 调 BMA 分类
        scenes: list[str] = await _call_bma_classify(message, recent_turns=recent_turns)

        # 路由决策
        scene: str
        if len(scenes) == 1:
            scene = scenes[0]
        elif len(scenes) > 1:
            scene = "orchestrator"
        else:
            scene = "guide"

        # 加载场景配置
        config: SceneConfig = _config_loader.get_scene(scene)

        # 设置 deps
        deps.current_scene = scene
        deps.available_tools = config.tools
        deps.allowed_skills = config.skills
        deps.current_scene_agent_md = config.agent_md if config.agent_md else None

        logger.info(
            "场景决策: user=%s, scene=%s, agent_md=%s, tools=%d, skills=%s",
            user_id, scene, config.agent_md, len(config.tools), config.skills,
        )

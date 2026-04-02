"""MainAgent 前置 Hook：根据用户状态判断阶段，动态加载 tools 和 skills。

升级到 S2 的路径：
1. 硬信号（UserStatService）— VIN / 下过单 / 绑车 / 已升级过 → S2
2. proceed_to_booking 工具调用 — 内部写入硬信号 + 即时切换到 S2

S2 场景路由：
- BMA 每轮分类用户意图 → 返回 scenes 列表
- 单场景 → 走专属配置（tools/skills/agent_md）
- 多场景 → 走 multi（全量工具）
- 空列表 → 走 none（极简配置）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 阶段配置（从 stage_config.yaml 加载）
# ============================================================


class StageConfig:
    """阶段配置：tools + skills + agent_md。"""

    def __init__(
        self,
        name: str,
        tools: list[str],
        skills: list[str],
        agent_md: str = "",
    ) -> None:
        self.name: str = name
        self.tools: list[str] = tools
        self.skills: list[str] = skills
        self.agent_md: str = agent_md


class StageConfigLoader:
    """加载 stage_config.yaml 中的阶段配置。

    S1 为扁平结构，S2 为嵌套结构（全部在 scenes 下，包含 none/multi/saving/shop/insurance）。
    """

    def __init__(self) -> None:
        self._stages: dict[str, StageConfig] = {}
        self._s2_scenes: dict[str, StageConfig] = {}
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

        stage_id: str
        stage_data: dict[str, Any]
        for stage_id, stage_data in raw.get("stages", {}).items():
            if stage_id == "S2":
                # S2 嵌套结构：所有配置在 scenes 下（none/multi/saving/shop/insurance）
                scenes_data: dict[str, Any] = stage_data.get("scenes", {})
                scene_id: str
                scene_cfg: dict[str, Any]
                for scene_id, scene_cfg in scenes_data.items():
                    self._s2_scenes[scene_id] = StageConfig(
                        name=f"S2-{scene_id}",
                        tools=scene_cfg.get("tools", []),
                        skills=scene_cfg.get("skills", []),
                        agent_md=scene_cfg.get("agent_md", ""),
                    )
                # _stages["S2"] 指向 multi，供 proceed_to_booking 等外部调用兼容
                if "multi" in self._s2_scenes:
                    self._stages[stage_id] = self._s2_scenes["multi"]
            else:
                # S1 等扁平结构
                self._stages[stage_id] = StageConfig(
                    name=stage_data.get("name", stage_id),
                    tools=stage_data.get("tools", []),
                    skills=stage_data.get("skills", []),
                    agent_md=stage_data.get("agent_md", ""),
                )

        self._loaded = True
        logger.info(
            "阶段配置加载完成: %d 个阶段, %d 个 S2 场景",
            len(self._stages),
            len(self._s2_scenes),
        )

    def get_stage(self, stage_id: str) -> StageConfig:
        """获取阶段配置（S2 返回 multi 配置，兼容外部调用）。"""
        self.ensure_loaded()
        if stage_id not in self._stages:
            raise KeyError(f"阶段 '{stage_id}' 不存在")
        return self._stages[stage_id]

    def get_s2_scene(self, scene: str) -> StageConfig:
        """获取 S2 场景配置。未匹配时回退到 multi。"""
        self.ensure_loaded()
        if scene in self._s2_scenes:
            return self._s2_scenes[scene]
        return self._s2_scenes["multi"]


# 模块级单例
_config_loader: StageConfigLoader = StageConfigLoader()


# ============================================================
# BMA 场景分类调用
# ============================================================


async def _call_bma_classify(message: str) -> list[str]:
    """调用 BMA /classify 接口进行场景分类。"""
    from src.config import BUSINESS_MAP_AGENT_URL

    url: str = f"{BUSINESS_MAP_AGENT_URL.rstrip('/')}/classify"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp: httpx.Response = await client.post(
                url,
                json={"message": message},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            scenes: list[str] = data.get("scenes", [])
            logger.info("BMA 场景分类: %s → %s", message[:50], scenes)
            return scenes
    except Exception:
        logger.warning("BMA 场景分类调用失败，回退到 none", exc_info=True)
        return []


# ============================================================
# Hook 实现
# ============================================================


class StageHook:
    """MainAgent 前置 Hook：查 UserStatService 硬信号判断 S1/S2，S2 时做场景路由。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        _config_loader.ensure_loaded()

        from hlsc.services.user_stat_service import user_stat_service

        stage: str = await user_stat_service.get_stage(user_id, session_id)
        logger.info("用户 %s → %s", user_id, stage)

        if stage == "S2":
            # S2 场景路由：调 BMA 分类
            scenes: list[str] = await _call_bma_classify(message)
            if len(scenes) == 1:
                scene: str = scenes[0]
            elif len(scenes) > 1:
                scene = "multi"
            else:
                scene = "none"

            config: StageConfig = _config_loader.get_s2_scene(scene)
            deps.current_stage = stage
            deps.current_scene = scene
            deps.available_tools = config.tools
            deps.allowed_skills = config.skills
            deps.current_scene_agent_md = config.agent_md if config.agent_md else None

            logger.info(
                "S2 场景决策: user=%s, scene=%s(%s), agent_md=%s, tools=%d, skills=%s",
                user_id, scene, config.name, config.agent_md,
                len(config.tools), config.skills,
            )
        else:
            # S1 扁平配置
            config = _config_loader.get_stage(stage)
            deps.current_stage = stage
            deps.available_tools = config.tools
            deps.allowed_skills = config.skills

            logger.info(
                "阶段决策: user=%s, stage=%s(%s), tools=%d, skills=%s",
                user_id, stage, config.name, len(config.tools), config.skills,
            )

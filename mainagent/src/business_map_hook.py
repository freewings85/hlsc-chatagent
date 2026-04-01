"""MainAgent 前置 Hook：根据用户状态判断阶段，动态加载 tools 和 skills。

升级到 S2 的路径：
1. 硬信号（UserStatService）— VIN / 下过单 / 绑车 / 已升级过 → S2
2. confirm_saving_plan 工具调用 — 内部调 upgrade_to_s2 写入硬信号 → 下一轮自动 S2

不依赖 BMA 做升级判断。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 阶段配置（从 stage_config.yaml 加载）
# ============================================================


class StageConfig:
    """阶段配置：tools + skills。"""

    def __init__(self, name: str, tools: list[str], skills: list[str]) -> None:
        self.name: str = name
        self.tools: list[str] = tools
        self.skills: list[str] = skills


class StageConfigLoader:
    """加载 stage_config.yaml 中的阶段配置。"""

    def __init__(self) -> None:
        self._stages: dict[str, StageConfig] = {}
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
            self._stages[stage_id] = StageConfig(
                name=stage_data.get("name", stage_id),
                tools=stage_data.get("tools", []),
                skills=stage_data.get("skills", []),
            )

        self._loaded = True
        logger.info("阶段配置加载完成: %d 个阶段", len(self._stages))

    def get_stage(self, stage_id: str) -> StageConfig:
        """获取阶段配置。"""
        self.ensure_loaded()
        if stage_id not in self._stages:
            raise KeyError(f"阶段 '{stage_id}' 不存在")
        return self._stages[stage_id]


# 模块级单例
_config_loader: StageConfigLoader = StageConfigLoader()


# ============================================================
# Hook 实现
# ============================================================


class StageHook:
    """MainAgent 前置 Hook：查 UserStatService 硬信号判断 S1/S2。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        _config_loader.ensure_loaded()

        from hlsc.services.user_stat_service import UserStat, user_stat_service

        stat: UserStat = await user_stat_service.get_user_stat(user_id)

        stage: str
        if user_stat_service.is_s2_by_hard_signal(stat):
            stage = "S2"
            logger.info(
                "用户 %s 硬信号命中 S2 (ordered=%s, vin=%s, car=%s)",
                user_id, stat.has_ordered, stat.has_vin, stat.has_bound_car,
            )
        else:
            stage = "S1"
            logger.info("用户 %s 无硬信号，S1", user_id)

        config: StageConfig = _config_loader.get_stage(stage)
        deps.current_stage = stage
        deps.available_tools = config.tools
        deps.allowed_skills = config.skills

        logger.info(
            "阶段决策: user=%s, stage=%s(%s), tools=%d, skills=%s",
            user_id, stage, config.name, len(config.tools), config.skills,
        )

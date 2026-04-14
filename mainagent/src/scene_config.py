"""SceneConfigRegistry —— stage_config.yaml 的统一解析与缓存。

所有需要读取场景配置（tools / skills / agent_md / prompt_parts / vars）的模块
统一通过本模块的 ``registry`` 单例访问，避免重复解析。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================


class SceneNotFoundError(Exception):
    """请求场景不在 stage_config.yaml 中——不在服务范围。"""

    def __init__(self, scene_id: str, available: list[str]) -> None:
        self.scene_id: str = scene_id
        self.available: list[str] = available
        super().__init__(
            f"场景 '{scene_id}' 不在服务范围。可用场景: {available}"
        )


@dataclass
class SceneConfig:
    """单个场景的完整配置。"""

    name: str
    prompt_parts: list[str] = field(default_factory=list)
    # agent_md 是一组文件路径（相对于 prompts/templates/），按顺序拼接成 agent_md 正文
    agent_md: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    vars: dict[str, str] = field(default_factory=dict)
    # raw 保留原始 dict，供 delegate 等需要完整字典的场景使用
    raw: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Registry 单例
# ============================================================


class SceneConfigRegistry:
    """stage_config.yaml 的统一解析与缓存（懒加载）。

    用法::

        from src.scene_config import registry
        cfg = registry.get_scene("platform")
        cfg.tools   # ["match_project", ...]
        cfg.vars    # {"key": "value"}
    """

    def __init__(self) -> None:
        self._scenes: dict[str, SceneConfig] = {}
        self._loaded: bool = False

    # ---- 核心：懒加载 --------------------------------------------------

    def ensure_loaded(self) -> None:
        """首次调用时解析 YAML，之后直接返回。"""
        if self._loaded:
            return

        config_path: Path = self._resolve_config_path()
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        scene_id: str
        scene_data: dict[str, Any]
        for scene_id, scene_data in raw.get("scenes", {}).items():
            raw_vars: dict[str, Any] = scene_data.get("vars", {})
            # agent_md 兼容：支持 list（新）或 str（老，自动转单元素 list）
            raw_agent_md: Any = scene_data.get("agent_md", [])
            agent_md_list: list[str] = (
                raw_agent_md if isinstance(raw_agent_md, list)
                else ([raw_agent_md] if raw_agent_md else [])
            )
            self._scenes[scene_id] = SceneConfig(
                name=scene_id,
                prompt_parts=scene_data.get("prompt_parts", []),
                agent_md=agent_md_list,
                tools=scene_data.get("tools", []),
                skills=scene_data.get("skills", []),
                vars={k: str(v) for k, v in raw_vars.items()},
                raw=dict(scene_data),
            )

        self._loaded = True
        logger.info("SceneConfigRegistry 加载完成: %d 个场景", len(self._scenes))

    # ---- 查询接口 ------------------------------------------------------

    def get_scene(self, scene_id: str) -> SceneConfig:
        """获取场景配置。未匹配时抛错（不在服务范围）。"""
        self.ensure_loaded()
        if scene_id in self._scenes:
            return self._scenes[scene_id]
        raise SceneNotFoundError(scene_id, list(self._scenes.keys()))

    def get_all_scenes(self) -> dict[str, SceneConfig]:
        """返回全部场景配置（只读视角）。"""
        self.ensure_loaded()
        return self._scenes

    def get_scene_prompt_parts(self, scene_id: str) -> list[str]:
        """获取指定场景的 prompt_parts 列表。"""
        return self.get_scene(scene_id).prompt_parts

    def get_scene_vars(self, scene_id: str) -> dict[str, str]:
        """获取指定场景的模板变量。"""
        return self.get_scene(scene_id).vars

    def get_all_prompt_parts_map(self) -> dict[str, list[str]]:
        """返回 {scene_id: prompt_parts} 映射（prompt_loader 兼容）。"""
        self.ensure_loaded()
        return {sid: cfg.prompt_parts for sid, cfg in self._scenes.items()}

    def get_scene_raw(self, scene_id: str) -> dict[str, Any]:
        """返回场景的原始 dict（delegate 兼容）。"""
        return self.get_scene(scene_id).raw

    def get_all_raw(self) -> dict[str, dict[str, Any]]:
        """返回 {scene_id: raw_dict} 映射（delegate 兼容）。"""
        self.ensure_loaded()
        return {sid: cfg.raw for sid, cfg in self._scenes.items()}

    # ---- 内部 ----------------------------------------------------------

    @staticmethod
    def _resolve_config_path() -> Path:
        """配置路径：优先环境变量，否则基于 __file__ 自动定位。"""
        config_path_str: str = os.getenv("STAGE_CONFIG_PATH", "")
        if config_path_str:
            return Path(config_path_str)
        # 默认：mainagent/stage_config.yaml（本文件在 mainagent/src/ 下）
        return Path(__file__).resolve().parent.parent / "stage_config.yaml"


# 模块级单例
registry: SceneConfigRegistry = SceneConfigRegistry()

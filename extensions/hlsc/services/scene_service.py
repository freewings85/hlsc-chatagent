"""场景配置服务：解析 scene_config.yaml 为类型化模型，提供场景查询能力。

配置路径优先从环境变量 ``SCENE_CONFIG_PATH`` 读取，回退到默认路径
``extensions/business-map/scene_config.yaml``。
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
# 数据模型
# ============================================================


@dataclass
class KeywordFactor:
    """关键词因子：字符串匹配，零成本。"""

    name: str
    keywords: list[str]


@dataclass
class BmaFactorBool:
    """BMA 布尔因子：小模型判断 true/false。"""

    name: str
    description: str


@dataclass
class BmaFactorEnum:
    """BMA 枚举因子：小模型从选项中选一个。"""

    name: str
    description: str
    options: list[str]


@dataclass
class BmaConfig:
    """BMA 并行调用配置。"""

    max_factors_per_call: int
    parallel_enabled: bool
    groups: list[dict[str, Any]]


@dataclass
class FactorConfig:
    """因子声明汇总。"""

    slot_factors: list[str]
    keyword_factors: list[KeywordFactor]
    bma_bool_factors: list[BmaFactorBool]
    bma_enum_factors: list[BmaFactorEnum]


@dataclass
class TreeNode:
    """决策树节点。

    YAML 中使用 ``if`` 作为条件 key（Python 保留字），解析时映射到 ``condition``。
    """

    condition: str | None = None
    scene: str | None = None
    children: list[TreeNode] | None = None
    label: str | None = None


@dataclass
class TargetSlot:
    """场景目标槽位定义。"""

    label: str
    required: str  # "true" | "conditional"
    method: str
    condition: str | None = None


@dataclass
class StageConfig:
    """阶段定义（S1/S2）。"""

    name: str
    description: str
    slots: dict[str, dict[str, str]]


@dataclass
class SceneConfig:
    """单个场景的完整定义。"""

    name: str
    stage: str
    goal: str
    target_slots: dict[str, TargetSlot]
    tools: list[str]
    skills: list[str]
    exit_when: str
    strategy: str


@dataclass
class SceneServiceConfig:
    """场景配置文件的顶层结构。"""

    factors: FactorConfig
    bma_config: BmaConfig
    stages: dict[str, StageConfig]
    tree: list[TreeNode]
    scenes: dict[str, SceneConfig]


# ============================================================
# 解析辅助函数
# ============================================================


def _parse_factors(raw: dict[str, Any]) -> FactorConfig:
    """解析 meta.factors 部分。"""
    slot_factors: list[str] = raw.get("slot_factors", [])

    keyword_factors: list[KeywordFactor] = [
        KeywordFactor(name=item["name"], keywords=item["keywords"])
        for item in raw.get("keyword_factors", [])
    ]

    bma_raw: dict[str, Any] = raw.get("bma_factors", {})
    bma_bool_factors: list[BmaFactorBool] = [
        BmaFactorBool(name=item["name"], description=item["description"])
        for item in bma_raw.get("bool", [])
    ]
    bma_enum_factors: list[BmaFactorEnum] = [
        BmaFactorEnum(
            name=item["name"],
            description=item["description"],
            options=item["options"],
        )
        for item in bma_raw.get("enum", [])
    ]

    return FactorConfig(
        slot_factors=slot_factors,
        keyword_factors=keyword_factors,
        bma_bool_factors=bma_bool_factors,
        bma_enum_factors=bma_enum_factors,
    )


def _parse_bma_config(raw: dict[str, Any]) -> BmaConfig:
    """解析 bma_config 部分。"""
    return BmaConfig(
        max_factors_per_call=int(raw["max_factors_per_call"]),
        parallel_enabled=bool(raw["parallel_enabled"]),
        groups=list(raw.get("groups", [])),
    )


def _parse_tree_node(raw: dict[str, Any]) -> TreeNode:
    """递归解析单个决策树节点。

    YAML 中 ``if`` 映射到 ``condition``。
    """
    condition: str | None = raw.get("if")
    scene: str | None = raw.get("scene")
    label: str | None = raw.get("label")

    children: list[TreeNode] | None = None
    raw_children: list[dict[str, Any]] | None = raw.get("children")
    if raw_children is not None:
        children = [_parse_tree_node(child) for child in raw_children]

    return TreeNode(
        condition=condition,
        scene=scene,
        children=children,
        label=label,
    )


def _parse_target_slots(raw: dict[str, Any] | None) -> dict[str, TargetSlot]:
    """解析场景的 target_slots 部分。

    YAML 中可能是空 dict ``{}``，此时直接返回空字典。
    """
    if not raw:
        return {}

    result: dict[str, TargetSlot] = {}
    slot_name: str
    slot_data: dict[str, str]
    for slot_name, slot_data in raw.items():
        result[slot_name] = TargetSlot(
            label=slot_data["label"],
            required=str(slot_data["required"]),
            method=slot_data["method"],
            condition=slot_data.get("condition"),
        )
    return result


def _parse_stages(raw: dict[str, Any]) -> dict[str, StageConfig]:
    """解析 stages 部分。"""
    result: dict[str, StageConfig] = {}
    stage_id: str
    stage_data: dict[str, Any]
    for stage_id, stage_data in raw.items():
        result[stage_id] = StageConfig(
            name=stage_data["name"],
            description=stage_data["description"],
            slots=stage_data.get("slots", {}),
        )
    return result


def _parse_scenes(raw: dict[str, Any]) -> dict[str, SceneConfig]:
    """解析 scenes 部分。"""
    result: dict[str, SceneConfig] = {}
    scene_id: str
    scene_data: dict[str, Any]
    for scene_id, scene_data in raw.items():
        target_slots: dict[str, TargetSlot] = _parse_target_slots(
            scene_data.get("target_slots")
        )
        result[scene_id] = SceneConfig(
            name=scene_data["name"],
            stage=scene_data["stage"],
            goal=scene_data["goal"],
            target_slots=target_slots,
            tools=scene_data.get("tools", []),
            skills=scene_data.get("skills", []),
            exit_when=str(scene_data["exit_when"]),
            strategy=str(scene_data.get("strategy", "")),
        )
    return result


# ============================================================
# 服务类
# ============================================================

# 默认配置路径
_DEFAULT_CONFIG_PATH: str = "extensions/business-map/scene_config.yaml"


class SceneService:
    """场景配置服务：加载 YAML 并提供类型化查询。"""

    def __init__(self) -> None:
        self._config: SceneServiceConfig | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def load(self, config_path: Path | None = None) -> None:
        """读取 YAML 文件，解析为 SceneServiceConfig。

        Args:
            config_path: 配置文件路径。为 None 时从环境变量
                ``SCENE_CONFIG_PATH`` 读取，再回退到默认路径。
        """
        if config_path is None:
            env_path: str | None = os.environ.get("SCENE_CONFIG_PATH")
            resolved_path: Path = (
                Path(env_path) if env_path else Path(_DEFAULT_CONFIG_PATH)
            )
        else:
            resolved_path = config_path

        logger.info("加载场景配置: %s", resolved_path)

        with open(resolved_path, encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        meta: dict[str, Any] = raw.get("meta", {})

        factors: FactorConfig = _parse_factors(meta.get("factors", {}))
        bma_config: BmaConfig = _parse_bma_config(
            raw.get("bma_config", meta.get("bma_config", {}))
        )
        stages: dict[str, StageConfig] = _parse_stages(raw.get("stages", {}))
        tree_nodes: list[TreeNode] = [
            _parse_tree_node(node) for node in raw.get("tree", [])
        ]
        scenes: dict[str, SceneConfig] = _parse_scenes(raw.get("scenes", {}))

        self._config = SceneServiceConfig(
            factors=factors,
            bma_config=bma_config,
            stages=stages,
            tree=tree_nodes,
            scenes=scenes,
        )

        logger.info(
            "场景配置加载完成: %d 个阶段, %d 个树节点, %d 个场景",
            len(stages),
            len(tree_nodes),
            len(scenes),
        )

    @property
    def is_loaded(self) -> bool:
        """是否已加载配置。"""
        return self._config is not None

    @property
    def config(self) -> SceneServiceConfig:
        """获取已加载的配置，未加载时抛异常。"""
        if self._config is None:
            raise RuntimeError("SceneService 尚未加载，请先调用 load()")
        return self._config

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_scene(self, scene_id: str) -> SceneConfig:
        """按 ID 获取场景配置，不存在抛 KeyError。"""
        scenes: dict[str, SceneConfig] = self.config.scenes
        if scene_id not in scenes:
            raise KeyError(f"场景 '{scene_id}' 不存在")
        return scenes[scene_id]


# 模块级单例
scene_service: SceneService = SceneService()

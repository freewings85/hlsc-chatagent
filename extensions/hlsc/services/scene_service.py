"""场景配置加载器：解析 scene_config.yaml 为类型化 Python 模型。

模块级单例 ``scene_service``，进程启动时调用 ``load()`` 一次。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================


@dataclass
class BoolFactor:
    """BMA bool 因子定义。"""

    name: str
    description: str


@dataclass
class EnumFactor:
    """BMA enum 因子定义。"""

    name: str
    description: str
    options: list[str]


@dataclass
class FactorsConfig:
    """因子声明（只有 BMA 因子）。"""

    bool_factors: list[BoolFactor] = field(default_factory=list)
    enum_factors: list[EnumFactor] = field(default_factory=list)


@dataclass
class TreeNode:
    """决策树节点。"""

    condition: str | None = None  # None 表示兜底节点
    scene: str | None = None
    children: list[TreeNode] = field(default_factory=list)


@dataclass
class SceneConfig:
    """场景定义：scene ID → name / tools / skills。"""

    id: str
    name: str
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)


@dataclass
class SceneServiceConfig:
    """完整配置。"""

    factors: FactorsConfig = field(default_factory=FactorsConfig)
    tree: list[TreeNode] = field(default_factory=list)
    scenes: dict[str, SceneConfig] = field(default_factory=dict)


# ============================================================
# 解析函数
# ============================================================


def _parse_factors(raw: dict[str, Any]) -> FactorsConfig:
    """解析 factors 段。"""
    bool_list: list[BoolFactor] = []
    enum_list: list[EnumFactor] = []

    raw_bool: list[dict[str, Any]]
    for raw_bool_item in raw.get("bool", []):
        bool_list.append(
            BoolFactor(name=raw_bool_item["name"], description=raw_bool_item["description"])
        )

    raw_enum_item: dict[str, Any]
    for raw_enum_item in raw.get("enum", []):
        enum_list.append(
            EnumFactor(
                name=raw_enum_item["name"],
                description=raw_enum_item["description"],
                options=raw_enum_item["options"],
            )
        )

    return FactorsConfig(bool_factors=bool_list, enum_factors=enum_list)


def _parse_tree(raw_nodes: list[dict[str, Any]]) -> list[TreeNode]:
    """递归解析决策树。"""
    nodes: list[TreeNode] = []
    raw: dict[str, Any]
    for raw in raw_nodes:
        node: TreeNode = TreeNode(
            condition=raw.get("if"),
            scene=raw.get("scene"),
            children=_parse_tree(raw["children"]) if "children" in raw else [],
        )
        nodes.append(node)
    return nodes


def _parse_scenes(raw: dict[str, Any]) -> dict[str, SceneConfig]:
    """解析 scenes 段。"""
    scenes: dict[str, SceneConfig] = {}
    scene_id: str
    scene_data: dict[str, Any]
    for scene_id, scene_data in raw.items():
        scenes[scene_id] = SceneConfig(
            id=scene_id,
            name=scene_data.get("name", scene_id),
            tools=scene_data.get("tools", []),
            skills=scene_data.get("skills", []),
        )
    return scenes


# ============================================================
# SceneService
# ============================================================


class SceneService:
    """场景配置服务（单例）。"""

    def __init__(self) -> None:
        self._config: SceneServiceConfig | None = None

    def load(self, config_path: Path) -> None:
        """加载 YAML 配置文件。"""
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        self._config = SceneServiceConfig(
            factors=_parse_factors(raw.get("factors", {})),
            tree=_parse_tree(raw.get("tree", [])),
            scenes=_parse_scenes(raw.get("scenes", {})),
        )
        logger.info(
            "SceneService 加载完成: %d 个因子, %d 棵树节点, %d 个场景",
            len(self._config.factors.bool_factors) + len(self._config.factors.enum_factors),
            len(self._config.tree),
            len(self._config.scenes),
        )

    @property
    def config(self) -> SceneServiceConfig:
        """获取配置，未加载时抛异常。"""
        if self._config is None:
            raise RuntimeError("SceneService 未加载，请先调用 load()")
        return self._config

    def get_scene(self, scene_id: str) -> SceneConfig:
        """按 ID 获取场景配置。"""
        scenes: dict[str, SceneConfig] = self.config.scenes
        if scene_id not in scenes:
            raise KeyError(f"场景 '{scene_id}' 不存在")
        return scenes[scene_id]


# 模块级单例
scene_service: SceneService = SceneService()

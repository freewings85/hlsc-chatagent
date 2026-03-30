"""场景配置服务测试。

覆盖：
- 加载 scene_config_example.yaml 成功
- 各模型字段正确解析
- get_scene 正常/不存在抛 KeyError
- TreeNode 的 if→condition 映射
- skills 字段正确解析
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hlsc.services.scene_service import (
    BmaConfig,
    BmaFactorBool,
    BmaFactorEnum,
    FactorConfig,
    KeywordFactor,
    SceneConfig,
    SceneService,
    SceneServiceConfig,
    StageConfig,
    TargetSlot,
    TreeNode,
    _parse_factors,
    _parse_target_slots,
    _parse_tree_node,
)

# ── 路径解析 ──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_EXAMPLE_CONFIG: Path = _PROJECT_ROOT / "extensions" / "business-map" / "scene_config_example.yaml"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def scene_service() -> SceneService:
    """加载 example 配置的 SceneService 实例。"""
    svc: SceneService = SceneService()
    svc.load(_EXAMPLE_CONFIG)
    return svc


@pytest.fixture
def config(scene_service: SceneService) -> SceneServiceConfig:
    """已加载的配置。"""
    return scene_service.config


# ============================================================
# 加载测试
# ============================================================


class TestSceneServiceLoad:
    """SceneService 加载测试。"""

    def test_load_success(self, scene_service: SceneService) -> None:
        """加载 example 配置文件成功。"""
        assert scene_service.is_loaded is True

    def test_not_loaded_raises(self) -> None:
        """未加载时访问 config 抛 RuntimeError。"""
        svc: SceneService = SceneService()
        assert svc.is_loaded is False
        with pytest.raises(RuntimeError, match="尚未加载"):
            _ = svc.config

    def test_load_nonexistent_file(self) -> None:
        """加载不存在的文件抛异常。"""
        svc: SceneService = SceneService()
        with pytest.raises(FileNotFoundError):
            svc.load(Path("/nonexistent/config.yaml"))


# ============================================================
# 因子配置解析测试
# ============================================================


class TestFactorsParsing:
    """因子配置解析测试。"""

    def test_slot_factors(self, config: SceneServiceConfig) -> None:
        """slot_factors 正确解析。"""
        factors: FactorConfig = config.factors
        assert "slot.project_id" in factors.slot_factors
        assert "slot.merchant" in factors.slot_factors
        assert len(factors.slot_factors) >= 5

    def test_keyword_factors(self, config: SceneServiceConfig) -> None:
        """keyword_factors 正确解析。"""
        factors: FactorConfig = config.factors
        assert len(factors.keyword_factors) >= 2
        kf: KeywordFactor = factors.keyword_factors[0]
        assert kf.name == "intent.has_urgent"
        assert "抛锚" in kf.keywords

    def test_bma_bool_factors(self, config: SceneServiceConfig) -> None:
        """BMA bool 因子正确解析。"""
        factors: FactorConfig = config.factors
        assert len(factors.bma_bool_factors) >= 2
        bf: BmaFactorBool = factors.bma_bool_factors[0]
        assert bf.name == "intent.has_car_service"
        assert bf.description != ""

    def test_bma_enum_factors(self, config: SceneServiceConfig) -> None:
        """BMA enum 因子正确解析。"""
        factors: FactorConfig = config.factors
        assert len(factors.bma_enum_factors) >= 3
        ef: BmaFactorEnum = factors.bma_enum_factors[0]
        assert ef.name == "intent.project_category"
        assert "轮胎" in ef.options
        assert "保险" in ef.options


# ============================================================
# BMA 配置测试
# ============================================================


class TestBmaConfig:
    """BMA 配置解析测试。"""

    def test_bma_config_fields(self, config: SceneServiceConfig) -> None:
        """BMA 配置字段正确。"""
        bma: BmaConfig = config.bma_config
        assert bma.max_factors_per_call == 10
        assert bma.parallel_enabled is True
        assert len(bma.groups) >= 2


# ============================================================
# 阶段配置测试
# ============================================================


class TestStagesParsing:
    """阶段配置解析测试。"""

    def test_stages_count(self, config: SceneServiceConfig) -> None:
        """阶段数量正确。"""
        assert "S1" in config.stages
        assert "S2" in config.stages

    def test_stage_fields(self, config: SceneServiceConfig) -> None:
        """阶段字段正确。"""
        s1: StageConfig = config.stages["S1"]
        assert s1.name == "初步建立"
        assert s1.description != ""
        assert "project_id" in s1.slots


# ============================================================
# 决策树解析测试
# ============================================================


class TestTreeParsing:
    """决策树解析测试。"""

    def test_tree_not_empty(self, config: SceneServiceConfig) -> None:
        """决策树非空。"""
        assert len(config.tree) > 0

    def test_if_to_condition_mapping(self) -> None:
        """YAML 的 if key 映射到 TreeNode.condition。"""
        raw: dict[str, str] = {"if": "slot.project_id", "scene": "DIRECT"}
        node: TreeNode = _parse_tree_node(raw)
        assert node.condition == "slot.project_id"
        assert node.scene == "DIRECT"

    def test_tree_node_with_children(self) -> None:
        """带 children 的节点解析。"""
        raw: dict = {
            "if": "slot.project_id",
            "label": "测试",
            "children": [
                {"if": "slot.merchant", "scene": "A"},
                {"scene": "B"},
            ],
        }
        node: TreeNode = _parse_tree_node(raw)
        assert node.condition == "slot.project_id"
        assert node.label == "测试"
        assert node.children is not None
        assert len(node.children) == 2
        assert node.children[0].condition == "slot.merchant"
        assert node.children[1].condition is None
        assert node.children[1].scene == "B"

    def test_tree_node_fallback(self) -> None:
        """兜底节点（无 if）。"""
        raw: dict = {"scene": "CASUAL_CHAT"}
        node: TreeNode = _parse_tree_node(raw)
        assert node.condition is None
        assert node.scene == "CASUAL_CHAT"

    def test_first_node_has_condition(self, config: SceneServiceConfig) -> None:
        """第一个节点有条件（紧急救援）。"""
        first: TreeNode = config.tree[0]
        assert first.condition is not None
        assert first.scene == "URGENT"

    def test_last_node_is_fallback(self, config: SceneServiceConfig) -> None:
        """最后一个节点是兜底（无条件）。"""
        last: TreeNode = config.tree[-1]
        assert last.condition is None
        assert last.scene == "CASUAL_CHAT"


# ============================================================
# 场景配置测试
# ============================================================


class TestScenesParsing:
    """场景配置解析测试。"""

    def test_scenes_count(self, config: SceneServiceConfig) -> None:
        """场景数量 > 0。"""
        assert len(config.scenes) > 0

    def test_scene_fields(self, config: SceneServiceConfig) -> None:
        """场景基本字段正确。"""
        scene: SceneConfig = config.scenes["DIRECT_PROJECT"]
        assert scene.name == "直接表达项目"
        assert scene.stage == "S1"
        assert scene.goal != ""
        assert scene.exit_when != ""
        assert scene.strategy != ""

    def test_scene_tools(self, config: SceneServiceConfig) -> None:
        """场景工具列表正确。"""
        scene: SceneConfig = config.scenes["DIRECT_PROJECT"]
        assert "match_project" in scene.tools
        assert "ask_user_car_info" in scene.tools

    def test_scene_skills(self, config: SceneServiceConfig) -> None:
        """场景 skills 字段正确解析。"""
        scene: SceneConfig = config.scenes["SAVING_PLAN"]
        assert "saving-strategy-guide" in scene.skills
        assert "price-inquiry" in scene.skills

    def test_scene_empty_skills(self, config: SceneServiceConfig) -> None:
        """无 skill 场景返回空列表。"""
        scene: SceneConfig = config.scenes["DIRECT_PROJECT"]
        assert scene.skills == []

    def test_scene_target_slots(self, config: SceneServiceConfig) -> None:
        """场景 target_slots 正确解析。"""
        scene: SceneConfig = config.scenes["DIRECT_PROJECT"]
        assert "project_id" in scene.target_slots
        ts: TargetSlot = scene.target_slots["project_id"]
        assert ts.label == "养车项目ID"
        assert ts.required == "True"  # YAML true → Python True → str(True) = "True"
        assert ts.method != ""

    def test_scene_target_slots_conditional(self, config: SceneServiceConfig) -> None:
        """条件性 target_slot 有 condition 字段。"""
        scene: SceneConfig = config.scenes["DIRECT_PROJECT"]
        ts: TargetSlot = scene.target_slots["vehicle_info"]
        assert ts.required == "conditional"
        assert ts.condition is not None

    def test_scene_empty_target_slots(self, config: SceneServiceConfig) -> None:
        """空 target_slots 场景（如 URGENT）返回空 dict。"""
        scene: SceneConfig = config.scenes["URGENT"]
        assert scene.target_slots == {}


# ============================================================
# get_scene 查询测试
# ============================================================


class TestGetScene:
    """get_scene 查询测试。"""

    def test_get_scene_normal(self, scene_service: SceneService) -> None:
        """正常获取场景。"""
        scene: SceneConfig = scene_service.get_scene("CASUAL_CHAT")
        assert scene.name == "闲聊"

    def test_get_scene_not_found(self, scene_service: SceneService) -> None:
        """不存在的场景抛 KeyError。"""
        with pytest.raises(KeyError, match="NOT_EXIST"):
            scene_service.get_scene("NOT_EXIST")


# ============================================================
# _parse_target_slots 辅助函数测试
# ============================================================


class TestParseTargetSlots:
    """_parse_target_slots 边界测试。"""

    def test_none_input(self) -> None:
        """None 输入返回空 dict。"""
        result: dict[str, TargetSlot] = _parse_target_slots(None)
        assert result == {}

    def test_empty_dict(self) -> None:
        """空 dict 输入返回空 dict。"""
        result: dict[str, TargetSlot] = _parse_target_slots({})
        assert result == {}

    def test_parse_factors_empty(self) -> None:
        """空因子配置返回默认值。"""
        result: FactorConfig = _parse_factors({})
        assert result.slot_factors == []
        assert result.keyword_factors == []
        assert result.bma_bool_factors == []
        assert result.bma_enum_factors == []

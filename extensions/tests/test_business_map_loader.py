"""BusinessMap 加载器和 BusinessNode 模型测试。

测试 YAML 业务树的加载、节点查找、路径计算、校验逻辑。
使用 extensions/business-map/data/ 下的示例 YAML 文件作为测试数据。
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from hlsc.business_map.loader import BusinessMap
from hlsc.business_map.model import BusinessNode

# ── 路径解析（兼容不同工作目录）──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"


# ── Fixtures ──


@pytest.fixture(scope="module")
def tree() -> BusinessMap:
    """加载示例 YAML 树（模块级复用）。"""
    return BusinessMap.load(_BUSINESS_MAP_DIR)


# ── 加载与基础结构 ──


class TestLoadSampleTree:
    """加载示例 YAML 树，验证整体结构。"""

    def test_root_has_3_children(self, tree: BusinessMap) -> None:
        """根节点有 3 个一级子节点：project_saving, merchant_search, booking"""
        root: BusinessNode = tree.root
        assert len(root.resolved_children) == 3
        child_ids: list[str] = [c.id for c in root.resolved_children]
        assert "project_saving" in child_ids
        assert "merchant_search" in child_ids
        assert "booking" in child_ids

    def test_total_node_count(self, tree: BusinessMap) -> None:
        """验证总节点数（17 个节点）"""
        all_ids: set[str] = tree.all_ids()
        # root(1) + project_saving 分支(10) + merchant_search 分支(4)
        # + booking 分支(3: booking, build_plan, execute) = 17
        assert len(all_ids) == 17

    def test_root_name(self, tree: BusinessMap) -> None:
        """验证根节点名称"""
        assert tree.root.name == "养车预订业务地图"

    def test_root_has_description(self, tree: BusinessMap) -> None:
        """验证根节点有 description"""
        assert tree.root.description is not None
        assert "需求沟通" in tree.root.description


# ── 节点查找 ──


class TestFindNode:
    """按 ID 查找节点。"""

    def test_find_existing_node(self, tree: BusinessMap) -> None:
        """按 ID 查找存在的节点"""
        node: BusinessNode = tree.find("fuzzy_intent")
        assert node.name == "模糊意图场景"

    def test_find_root(self, tree: BusinessMap) -> None:
        """查找根节点"""
        node: BusinessNode = tree.find("root")
        assert node.id == "root"
        assert node is tree.root

    def test_find_intermediate_node(self, tree: BusinessMap) -> None:
        """查找中间节点"""
        node: BusinessNode = tree.find("confirm_project")
        assert node.name == "确认养车项目"
        assert node.children is not None
        assert len(node.children) == 3

    def test_find_nonexistent_raises(self, tree: BusinessMap) -> None:
        """查找不存在的 ID 抛 KeyError"""
        with pytest.raises(KeyError, match="不存在"):
            tree.find("nonexistent_node")


# ── 路径计算 ──


class TestPathFromRoot:
    """验证从根到目标节点的路径。"""

    def test_path_from_root_depth_3(self, tree: BusinessMap) -> None:
        """验证 fuzzy_intent 的路径深度"""
        node: BusinessNode = tree.find("fuzzy_intent")
        path: list[BusinessNode] = tree.path_from_root(node)
        # 路径：root → project_saving → confirm_project → fuzzy_intent
        assert len(path) == 4
        path_ids: list[str] = [n.id for n in path]
        assert path_ids == ["root", "project_saving", "confirm_project", "fuzzy_intent"]

    def test_path_from_root_depth_1(self, tree: BusinessMap) -> None:
        """验证一级节点路径"""
        node: BusinessNode = tree.find("project_saving")
        path: list[BusinessNode] = tree.path_from_root(node)
        # 路径：root → project_saving
        assert len(path) == 2
        assert path[0].id == "root"
        assert path[1].id == "project_saving"

    def test_path_from_root_root(self, tree: BusinessMap) -> None:
        """根节点路径只有自己"""
        path: list[BusinessNode] = tree.path_from_root(tree.root)
        assert len(path) == 1
        assert path[0].id == "root"

    def test_path_from_root_depth_2(self, tree: BusinessMap) -> None:
        """验证二级节点路径"""
        node: BusinessNode = tree.find("confirm_saving")
        path: list[BusinessNode] = tree.path_from_root(node)
        # 路径：root → project_saving → confirm_saving
        assert len(path) == 3
        path_ids: list[str] = [n.id for n in path]
        assert path_ids == ["root", "project_saving", "confirm_saving"]

    def test_path_coupon_path_depth_3(self, tree: BusinessMap) -> None:
        """验证 coupon_path 的路径深度"""
        node: BusinessNode = tree.find("coupon_path")
        path: list[BusinessNode] = tree.path_from_root(node)
        # 路径：root → project_saving → confirm_saving → coupon_path
        assert len(path) == 4
        path_ids: list[str] = [n.id for n in path]
        assert path_ids == ["root", "project_saving", "confirm_saving", "coupon_path"]


# ── all_ids ──


class TestAllIds:
    """验证 all_ids 返回完整 ID 集合。"""

    def test_all_ids_contains_expected(self, tree: BusinessMap) -> None:
        """all_ids 必须包含所有期望的节点"""
        all_ids: set[str] = tree.all_ids()
        expected: set[str] = {
            "root",
            "project_saving",
            "confirm_project",
            "direct_expression",
            "fuzzy_intent",
            "symptom_based",
            "confirm_requirements",
            "confirm_saving",
            "coupon_path",
            "bidding_path",
            "merchant_search",
            "search",
            "compare",
            "confirm",
            "booking",
            "build_plan",
            "execute",
        }
        assert expected.issubset(all_ids), f"缺少节点: {expected - all_ids}"

    def test_all_ids_no_extra(self, tree: BusinessMap) -> None:
        """不应有意外的额外节点"""
        all_ids: set[str] = tree.all_ids()
        assert len(all_ids) == 17


# ── parent_id ──


class TestParentId:
    """验证 parent_id 在加载时正确设置。"""

    def test_fuzzy_intent_parent(self, tree: BusinessMap) -> None:
        """fuzzy_intent.parent_id == confirm_project"""
        node: BusinessNode = tree.find("fuzzy_intent")
        assert node.parent_id == "confirm_project"

    def test_confirm_project_parent(self, tree: BusinessMap) -> None:
        """confirm_project.parent_id == project_saving"""
        node: BusinessNode = tree.find("confirm_project")
        assert node.parent_id == "project_saving"

    def test_project_saving_parent(self, tree: BusinessMap) -> None:
        """project_saving.parent_id == root"""
        node: BusinessNode = tree.find("project_saving")
        assert node.parent_id == "root"

    def test_root_has_no_parent(self, tree: BusinessMap) -> None:
        """根节点没有 parent_id"""
        assert tree.root.parent_id is None

    def test_booking_parent(self, tree: BusinessMap) -> None:
        """booking.parent_id == root"""
        node: BusinessNode = tree.find("booking")
        assert node.parent_id == "root"

    def test_coupon_path_parent(self, tree: BusinessMap) -> None:
        """coupon_path.parent_id == confirm_saving"""
        node: BusinessNode = tree.find("coupon_path")
        assert node.parent_id == "confirm_saving"


# ── resolved_children ──


class TestResolvedChildren:
    """验证 resolved_children 在加载时填充。"""

    def test_root_resolved_children(self, tree: BusinessMap) -> None:
        """根节点的 resolved_children 有 3 个 BusinessNode 对象"""
        root: BusinessNode = tree.root
        assert len(root.resolved_children) == 3
        for child in root.resolved_children:
            assert isinstance(child, BusinessNode)

    def test_confirm_project_resolved_children(self, tree: BusinessMap) -> None:
        """confirm_project 的 resolved_children 有 3 个节点"""
        node: BusinessNode = tree.find("confirm_project")
        assert len(node.resolved_children) == 3
        child_ids: list[str] = [c.id for c in node.resolved_children]
        assert "direct_expression" in child_ids
        assert "fuzzy_intent" in child_ids
        assert "symptom_based" in child_ids

    def test_merchant_search_resolved_children(self, tree: BusinessMap) -> None:
        """merchant_search 的 resolved_children 有 3 个节点"""
        node: BusinessNode = tree.find("merchant_search")
        assert len(node.resolved_children) == 3


# ── 模型校验 ──


class TestNodeValidation:
    """BusinessNode 的 Pydantic 校验逻辑。"""

    def test_description_or_checklist_required(self) -> None:
        """description 和 checklist 不能同时为空"""
        with pytest.raises(ValidationError, match="不能同时为空"):
            BusinessNode(id="bad_node", name="空节点")

    def test_description_only_is_valid(self) -> None:
        """只有 description 是合法的"""
        node: BusinessNode = BusinessNode(
            id="desc_only", name="只有描述", description="一些描述"
        )
        assert node.description == "一些描述"
        assert node.checklist is None

    def test_checklist_only_is_valid(self) -> None:
        """只有 checklist 是合法的"""
        node: BusinessNode = BusinessNode(
            id="cl_only", name="只有清单", checklist=["项目1", "项目2"]
        )
        assert node.description is None
        assert len(node.checklist) == 2

    def test_both_description_and_checklist(self) -> None:
        """description 和 checklist 都有也是合法的"""
        node: BusinessNode = BusinessNode(
            id="both",
            name="都有",
            description="描述",
            checklist=["项目1"],
        )
        assert node.description == "描述"
        assert node.checklist is not None


# ── 重复 ID ──


class TestUniqueIdViolation:
    """重复 ID 加载时抛 ValueError。"""

    def test_duplicate_id_raises(self, tmp_path: Path) -> None:
        """重复 ID 加载时抛 ValueError"""
        # 创建带有重复 ID 的临时 YAML 文件
        root_yaml: str = dedent("""\
            id: root
            name: 测试根
            description: 测试根描述
            children:
              - id: child_a
                name: 子节点A
                keywords: [a]
                path: child-a/
        """)
        (tmp_path / "_root.yaml").write_text(root_yaml, encoding="utf-8")

        # 子目录中创建一个与根节点 ID 冲突的 _node.yaml
        child_dir: Path = tmp_path / "child-a"
        child_dir.mkdir()
        # 故意使用与 root 不同但在树中会重复的 ID
        # 方案：两个子节点使用相同 ID
        dup_yaml: str = dedent("""\
            id: child_a
            name: 子节点A
            description: 子节点A描述
            children:
              - id: dup_node
                name: 重复节点
                keywords: [dup]
        """)
        (child_dir / "_node.yaml").write_text(dup_yaml, encoding="utf-8")

        # 创建另一个也叫 dup_node 的文件
        dup_yaml2: str = dedent("""\
            id: dup_node
            name: 重复节点2
            description: 这个 ID 重复了
        """)
        # 在 child-a 目录下放一个 dup-node.yaml
        (child_dir / "dup-node.yaml").write_text(dup_yaml2, encoding="utf-8")

        # 再创建一个同名 ID 的文件（不同路径）——模拟重复
        # 我们在 root 下再放一个 dup-node.yaml
        dup_yaml3: str = dedent("""\
            id: dup_node
            name: 又一个重复
            description: 第二个 dup_node
        """)
        (tmp_path / "dup-node.yaml").write_text(dup_yaml3, encoding="utf-8")

        # 修改 root 的 children 让它也引用 dup_node
        root_yaml_v2: str = dedent("""\
            id: root
            name: 测试根
            description: 测试根描述
            children:
              - id: child_a
                name: 子节点A
                keywords: [a]
                path: child-a/
              - id: dup_node
                name: 重复节点直接引用
                keywords: [dup]
        """)
        (tmp_path / "_root.yaml").write_text(root_yaml_v2, encoding="utf-8")

        with pytest.raises(ValueError, match="重复的节点 ID"):
            BusinessMap.load(tmp_path)


# ── 叶节点 ──


class TestLeafNode:
    """叶节点行为验证。"""

    def test_leaf_node_has_no_children(self, tree: BusinessMap) -> None:
        """叶节点没有 children"""
        node: BusinessNode = tree.find("fuzzy_intent")
        assert node.children is None
        assert node.resolved_children == []

    def test_direct_expression_is_leaf(self, tree: BusinessMap) -> None:
        """direct_expression 也是叶节点"""
        node: BusinessNode = tree.find("direct_expression")
        assert node.children is None
        assert node.resolved_children == []

    def test_booking_has_children(self, tree: BusinessMap) -> None:
        """booking 是中间节点，有 build_plan 和 execute 两个子节点"""
        node: BusinessNode = tree.find("booking")
        assert node.children is not None
        assert len(node.resolved_children) == 2

    def test_leaf_has_description(self, tree: BusinessMap) -> None:
        """叶节点仍然有 description（7.3 节约束）"""
        node: BusinessNode = tree.find("fuzzy_intent")
        assert node.description is not None
        assert "模糊" in node.description or "保养" in node.description


# ── 边界情况 ──


class TestEdgeCases:
    """边界情况和错误处理。"""

    def test_load_nonexistent_dir_raises(self) -> None:
        """加载不存在的目录抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            BusinessMap.load("/nonexistent/path/business-map")

    def test_load_dir_without_root_raises(self, tmp_path: Path) -> None:
        """目录中没有 _root.yaml 抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="_root.yaml"):
            BusinessMap.load(tmp_path)

    def test_node_with_depends_on(self, tree: BusinessMap) -> None:
        """验证带 depends_on 的节点"""
        node: BusinessNode = tree.find("fuzzy_intent")
        assert node.depends_on is not None
        assert len(node.depends_on) == 2

    def test_node_with_cancel_directions(self, tree: BusinessMap) -> None:
        """验证带 cancel_directions 的节点"""
        node: BusinessNode = tree.find("confirm_project")
        assert node.cancel_directions is not None
        assert len(node.cancel_directions) == 2

    def test_node_with_output(self, tree: BusinessMap) -> None:
        """验证带 output 的节点"""
        node: BusinessNode = tree.find("project_saving")
        assert node.output is not None
        assert len(node.output) == 3

    def test_load_nonexistent_dir_no_root_file(self, tmp_path: Path) -> None:
        """空目录（无 _root.yaml）加载失败"""
        with pytest.raises(FileNotFoundError):
            BusinessMap.load(tmp_path)

    def test_yaml_not_dict_raises_value_error(self, tmp_path: Path) -> None:
        """YAML 文件内容不是 dict（例如是列表）时抛 ValueError"""
        root_file: Path = tmp_path / "_root.yaml"
        root_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="应为 dict"):
            BusinessMap.load(tmp_path)

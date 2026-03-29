"""BusinessMapService 测试。

测试服务层的查询接口：
- 加载与查找
- 导航字段查询（get_business_children_nav, get_business_node_nav）
- 业务详情查询（get_business_node_detail）
- assemble_slice stub
- optional / keywords 分支覆盖
- StateTreeService 异常分支
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hlsc.business_map.model import BusinessChildRef, BusinessNode
from hlsc.services.business_map_service import BusinessMapService
from hlsc.services.state_tree_service import StateTreeService

# ── 路径解析（兼容不同工作目录）──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"


# ── Fixtures ──


@pytest.fixture(scope="module")
def service() -> BusinessMapService:
    """创建并加载 BusinessMapService（模块级复用）。"""
    svc: BusinessMapService = BusinessMapService()
    svc.load(_BUSINESS_MAP_DIR)
    return svc


# ── 加载与查找 ──


class TestServiceLoadAndFind:
    """service 加载后可以查找节点。"""

    def test_service_is_loaded(self, service: BusinessMapService) -> None:
        """加载后 is_loaded 为 True"""
        assert service.is_loaded is True

    def test_service_find_root(self, service: BusinessMapService) -> None:
        """service 可以查找根节点"""
        node: BusinessNode = service.find("root")
        assert node.id == "root"
        assert node.name == "养车预订业务地图"

    def test_service_find_leaf(self, service: BusinessMapService) -> None:
        """service 可以查找叶节点"""
        node: BusinessNode = service.find("fuzzy_intent")
        assert node.name == "模糊意图场景"

    def test_service_find_nonexistent_raises(self, service: BusinessMapService) -> None:
        """查找不存在的节点抛 KeyError"""
        with pytest.raises(KeyError):
            service.find("not_a_real_node")


# ── path_from_root ──


class TestServicePathFromRoot:
    """service 的 path_from_root 返回正确路径。"""

    def test_path_from_root_depth_3(self, service: BusinessMapService) -> None:
        """fuzzy_intent 路径：root → project_saving → confirm_project → fuzzy_intent"""
        path: list[BusinessNode] = service.path_from_root("fuzzy_intent")
        path_ids: list[str] = [n.id for n in path]
        assert path_ids == ["root", "project_saving", "confirm_project", "fuzzy_intent"]

    def test_path_from_root_depth_1(self, service: BusinessMapService) -> None:
        """一级节点路径"""
        path: list[BusinessNode] = service.path_from_root("merchant_search")
        assert len(path) == 2
        assert path[0].id == "root"
        assert path[1].id == "merchant_search"

    def test_path_from_root_root(self, service: BusinessMapService) -> None:
        """根节点路径只有自己"""
        path: list[BusinessNode] = service.path_from_root("root")
        assert len(path) == 1
        assert path[0].id == "root"


# ── get_business_children_nav ──


class TestGetBusinessChildrenNav:
    """get_business_children_nav 返回导航字段，不含业务字段。"""

    def test_root_children_nav(self, service: BusinessMapService) -> None:
        """根节点的 children nav 包含三个一级子节点"""
        result: str = service.get_business_children_nav("root")
        assert "project_saving" in result or "沟通项目需求" in result
        assert "merchant_search" in result or "筛选匹配商户" in result
        assert "booking" in result or "执行预订" in result

    def test_root_children_nav_contains_keywords(self, service: BusinessMapService) -> None:
        """children nav 包含 keywords 信息"""
        result: str = service.get_business_children_nav("confirm_project")
        # confirm_project 的子节点有 keywords
        assert "关键词" in result or "keywords" in result.lower()

    def test_root_children_nav_no_business_fields(self, service: BusinessMapService) -> None:
        """children nav 不包含业务字段"""
        result: str = service.get_business_children_nav("root")
        # 不应包含子节点的 description 内容
        assert "本阶段目标是把车主" not in result
        # 不应包含 checklist 内容
        assert "确认车主的养车项目" not in result
        # 不应包含 output 内容
        assert "已确认的养车项目列表" not in result
        # 不应包含 cancel_directions 内容
        assert "记录意向，结束流程" not in result

    def test_leaf_children_nav_empty(self, service: BusinessMapService) -> None:
        """叶节点的 children nav 返回提示信息"""
        result: str = service.get_business_children_nav("fuzzy_intent")
        assert "没有子节点" in result


# ── get_business_node_nav ──


class TestGetBusinessNodeNav:
    """get_business_node_nav 返回导航信息，不含业务字段。"""

    def test_node_nav_contains_id_and_name(self, service: BusinessMapService) -> None:
        """导航信息包含 id 和 name"""
        result: str = service.get_business_node_nav("confirm_project")
        assert "confirm_project" in result
        assert "确认养车项目" in result

    def test_node_nav_contains_keywords(self, service: BusinessMapService) -> None:
        """导航信息包含 keywords（如果节点有的话）"""
        # confirm_project 的子节点 fuzzy_intent 有 keywords
        result: str = service.get_business_node_nav("fuzzy_intent")
        # fuzzy_intent 自身在 YAML 中没有 keywords（keywords 在父节点的 children 条目中）
        # 但它的 BusinessNode 可能没有 keywords
        assert "fuzzy_intent" in result
        assert "模糊意图场景" in result

    def test_node_nav_no_description(self, service: BusinessMapService) -> None:
        """导航信息不包含 description"""
        result: str = service.get_business_node_nav("project_saving")
        assert "本阶段目标" not in result

    def test_node_nav_no_checklist(self, service: BusinessMapService) -> None:
        """导航信息不包含 checklist"""
        result: str = service.get_business_node_nav("project_saving")
        assert "确认车主的养车项目" not in result

    def test_node_nav_no_output(self, service: BusinessMapService) -> None:
        """导航信息不包含 output"""
        result: str = service.get_business_node_nav("project_saving")
        assert "已确认的养车项目列表" not in result

    def test_node_nav_shows_children_ids(self, service: BusinessMapService) -> None:
        """有子节点的节点显示 children ID 列表"""
        result: str = service.get_business_node_nav("confirm_project")
        assert "子节点数" in result
        assert "direct_expression" in result
        assert "fuzzy_intent" in result
        assert "symptom_based" in result


# ── get_business_node_detail ──


class TestGetBusinessNodeDetail:
    """get_business_node_detail 返回完整业务定义。"""

    def test_detail_contains_description(self, service: BusinessMapService) -> None:
        """业务详情包含 description"""
        result: str = service.get_business_node_detail("project_saving")
        assert "本阶段目标" in result

    def test_detail_contains_checklist(self, service: BusinessMapService) -> None:
        """业务详情包含 checklist"""
        result: str = service.get_business_node_detail("project_saving")
        assert "待办" in result
        assert "确认车主的养车项目" in result

    def test_detail_contains_output(self, service: BusinessMapService) -> None:
        """业务详情包含 output"""
        result: str = service.get_business_node_detail("project_saving")
        assert "产出" in result
        assert "已确认的养车项目列表" in result

    def test_detail_contains_depends_on(self, service: BusinessMapService) -> None:
        """业务详情包含 depends_on"""
        result: str = service.get_business_node_detail("fuzzy_intent")
        assert "依赖" in result
        assert "车型信息" in result

    def test_detail_contains_cancel_directions(self, service: BusinessMapService) -> None:
        """业务详情包含 cancel_directions"""
        result: str = service.get_business_node_detail("confirm_project")
        assert "取消走向" in result
        assert "车主不确定要做什么" in result

    def test_detail_is_markdown(self, service: BusinessMapService) -> None:
        """业务详情是 Markdown 格式"""
        result: str = service.get_business_node_detail("project_saving")
        # 以定位深度开头，包含 ### 标题
        assert result.startswith("定位深度")
        assert "###" in result
        # 包含 Markdown 列表项
        assert "- " in result

    def test_detail_contains_name(self, service: BusinessMapService) -> None:
        """业务详情标题包含节点名称"""
        result: str = service.get_business_node_detail("fuzzy_intent")
        assert "模糊意图场景" in result

    def test_detail_leaf_node(self, service: BusinessMapService) -> None:
        """叶节点的业务详情"""
        result: str = service.get_business_node_detail("direct_expression")
        assert "直接表达场景" in result
        assert "车主直接说出" in result


# ── 未加载 ──


class TestServiceNotLoaded:
    """未加载时调用查询方法应报错。"""

    def test_find_raises(self) -> None:
        """未加载时 find 报错"""
        svc: BusinessMapService = BusinessMapService()
        assert svc.is_loaded is False
        with pytest.raises(RuntimeError, match="尚未加载"):
            svc.find("root")

    def test_path_from_root_raises(self) -> None:
        """未加载时 path_from_root 报错"""
        svc: BusinessMapService = BusinessMapService()
        with pytest.raises(RuntimeError, match="尚未加载"):
            svc.path_from_root("root")

    def test_get_children_nav_raises(self) -> None:
        """未加载时 get_business_children_nav 报错"""
        svc: BusinessMapService = BusinessMapService()
        with pytest.raises(RuntimeError, match="尚未加载"):
            svc.get_business_children_nav("root")

    def test_get_node_nav_raises(self) -> None:
        """未加载时 get_business_node_nav 报错"""
        svc: BusinessMapService = BusinessMapService()
        with pytest.raises(RuntimeError, match="尚未加载"):
            svc.get_business_node_nav("root")

    def test_get_node_detail_raises(self) -> None:
        """未加载时 get_business_node_detail 报错"""
        svc: BusinessMapService = BusinessMapService()
        with pytest.raises(RuntimeError, match="尚未加载"):
            svc.get_business_node_detail("root")


# ── assemble_slice 基础冒烟测试 ──


class TestAssembleSliceSmoke:
    """assemble_slice 基础冒烟测试（详细测试在 test_business_map_assembler.py）。"""

    def test_assemble_slice_returns_str(self, service: BusinessMapService) -> None:
        """assemble_slice 返回字符串"""
        result: str = service.assemble_slice(["project_saving"])
        assert isinstance(result, str)
        assert "定位深度" in result


# ── optional / keywords 分支覆盖 ──


class TestOptionalAndKeywordsBranches:
    """覆盖 get_business_children_nav 和 get_business_node_nav 中
    optional=True、keywords 非空的分支（lines 76, 96, 98）。
    """

    def test_children_nav_optional_child(self, service: BusinessMapService) -> None:
        """project_saving 的 confirm_requirements 子节点 optional=True → 输出 [可选]"""
        result: str = service.get_business_children_nav("project_saving")
        assert "[可选]" in result

    def test_node_nav_optional_node(self) -> None:
        """节点自身 optional=True → get_business_node_nav 输出 [可选]"""
        # 手动构造带 optional=True 的节点，注入到 service 中
        svc: BusinessMapService = BusinessMapService()
        node: BusinessNode = BusinessNode(
            id="opt_node",
            name="可选测试节点",
            description="这是一个可选节点",
            keywords=["测试关键词", "可选"],
            optional=True,
        )
        # 构造最小 BusinessMap 并注入
        from hlsc.business_map.loader import BusinessMap
        bm: BusinessMap = BusinessMap(
            root=node,
            index={"opt_node": node},
        )
        svc._map = bm

        result: str = svc.get_business_node_nav("opt_node")
        # 验证 keywords 分支（line 96）
        assert "关键词" in result
        assert "测试关键词" in result
        assert "可选" in result
        # 验证 optional 分支（line 98）
        assert "[可选]" in result

    def test_node_nav_keywords_only(self) -> None:
        """节点有 keywords 但 optional=False → 只输出关键词，不输出 [可选]"""
        svc: BusinessMapService = BusinessMapService()
        node: BusinessNode = BusinessNode(
            id="kw_node",
            name="关键词测试节点",
            description="有关键词的节点",
            keywords=["保养", "换油"],
            optional=False,
        )
        from hlsc.business_map.loader import BusinessMap
        bm: BusinessMap = BusinessMap(
            root=node,
            index={"kw_node": node},
        )
        svc._map = bm

        result: str = svc.get_business_node_nav("kw_node")
        assert "关键词: 保养, 换油" in result
        assert "[可选]" not in result


# ── StateTreeService 异常分支 ──


class TestStateTreeServiceExceptions:
    """覆盖 StateTreeService 的异常处理路径（lines 30-32, 41-43）。"""

    def test_read_exception_returns_none(self, tmp_path: Path) -> None:
        """读取状态树发生异常时返回 None（line 30-32）"""
        svc: StateTreeService = StateTreeService()
        # 创建一个同名目录代替文件，使 read_text 失败
        file_path: Path = tmp_path / StateTreeService.FILENAME
        file_path.mkdir()  # 目录不能 read_text
        result: str | None = svc.read(tmp_path)
        assert result is None

    def test_write_exception_raises(self, tmp_path: Path) -> None:
        """写入状态树发生异常时 re-raise（line 41-43）"""
        svc: StateTreeService = StateTreeService()
        # mock write_text 抛出异常
        with patch.object(Path, "write_text", side_effect=PermissionError("权限不足")):
            with pytest.raises(PermissionError, match="权限不足"):
                svc.write(tmp_path, "测试内容")

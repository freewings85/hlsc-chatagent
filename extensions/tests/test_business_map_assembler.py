"""BusinessMapService 内容组装层测试。

测试 assemble_slice() 和 format_node() 的输出：
- 浅定位（第 1 层）
- 深定位（第 3 层）
- 多路径命中
- 无效 ID 跳过
- 祖先-后代去重
- 空列表
- 单个根节点
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hlsc.business_map.model import BusinessNode
from hlsc.services.business_map_service import BusinessMapService

# ── 路径解析（兼容不同工作目录）──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "mainagent" / "business-map"


# ── Fixtures ──


@pytest.fixture(scope="module")
def service() -> BusinessMapService:
    """创建并加载 BusinessMapService（模块级复用）。"""
    svc: BusinessMapService = BusinessMapService()
    svc.load(_BUSINESS_MAP_DIR)
    return svc


# ── format_node 测试 ──


class TestFormatNode:
    """format_node 把单个节点格式化为 Markdown 段落。"""

    def test_format_root(self, service: BusinessMapService) -> None:
        """根节点格式化：标题 + description"""
        node: BusinessNode = service.find("root")
        result: str = service.format_node(node)
        assert result.startswith("### 养车预订业务地图")
        assert "帮助车主完成从需求沟通到预订执行的完整流程。" in result

    def test_format_node_with_checklist(self, service: BusinessMapService) -> None:
        """带 checklist 的节点包含待办列表"""
        node: BusinessNode = service.find("project_saving")
        result: str = service.format_node(node)
        assert "待办：" in result
        assert "- 确认车主的养车项目" in result
        assert "- 了解是否有特殊需求" in result
        assert "- 沟通省钱方法和偏好" in result

    def test_format_node_with_output(self, service: BusinessMapService) -> None:
        """带 output 的节点包含产出列表"""
        node: BusinessNode = service.find("project_saving")
        result: str = service.format_node(node)
        assert "产出：" in result
        assert "- 已确认的养车项目列表" in result
        assert "- 特殊需求记录（如有）" in result
        assert "- 省钱方案偏好" in result

    def test_format_node_with_depends_on(self, service: BusinessMapService) -> None:
        """带 depends_on 的节点包含依赖列表"""
        node: BusinessNode = service.find("fuzzy_intent")
        result: str = service.format_node(node)
        assert "依赖：" in result
        assert "- 车型信息" in result
        assert "- 里程或上次保养时间" in result

    def test_format_node_with_cancel_directions(self, service: BusinessMapService) -> None:
        """带 cancel_directions 的节点包含取消走向（使用 → 箭头）"""
        node: BusinessNode = service.find("project_saving")
        result: str = service.format_node(node)
        assert "取消走向：" in result
        assert "- 车主不想做了 → 记录意向，结束流程" in result
        assert "- 车主要自己去店里问 → 提供商户推荐后结束" in result

    def test_format_node_description_stripped(self, service: BusinessMapService) -> None:
        """description 首尾空白被去除"""
        node: BusinessNode = service.find("root")
        result: str = service.format_node(node)
        # YAML 的 | 块标量末尾有换行，格式化后应被 strip
        lines: list[str] = result.split("\n")
        # 标题行之后紧接 description 第一行，不应有空行
        assert lines[1] == "帮助车主完成从需求沟通到预订执行的完整流程。"

    def test_format_node_no_optional_fields(self, service: BusinessMapService) -> None:
        """只有 description 没有 checklist/output/depends_on/cancel_directions 的节点"""
        # root 没有 checklist，只有 description
        node: BusinessNode = service.find("root")
        result: str = service.format_node(node)
        assert "待办：" not in result
        assert "产出：" not in result
        assert "依赖：" not in result
        assert "取消走向：" not in result


# ── assemble_slice 浅定位测试（section 10.2）──


class TestAssembleSliceShallow:
    """浅定位：node_ids=["project_saving"]，路径 root → project_saving，深度 1。"""

    def test_shallow_header(self, service: BusinessMapService) -> None:
        """头部显示定位深度 1，无多路径标记"""
        result: str = service.assemble_slice(["project_saving"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：1"

    def test_shallow_contains_root(self, service: BusinessMapService) -> None:
        """包含根节点内容"""
        result: str = service.assemble_slice(["project_saving"])
        assert "### 养车预订业务地图" in result
        assert "帮助车主完成从需求沟通到预订执行的完整流程。" in result

    def test_shallow_contains_target(self, service: BusinessMapService) -> None:
        """包含目标节点 project_saving 的完整业务内容"""
        result: str = service.assemble_slice(["project_saving"])
        assert "### 沟通项目需求与省钱方案" in result
        assert "本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。" in result
        assert "待办：" in result
        assert "- 确认车主的养车项目" in result
        assert "产出：" in result
        assert "- 已确认的养车项目列表" in result
        assert "取消走向：" in result
        assert "- 车主不想做了 → 记录意向，结束流程" in result

    def test_shallow_no_separator(self, service: BusinessMapService) -> None:
        """单路径无 --- 分隔符"""
        result: str = service.assemble_slice(["project_saving"])
        assert "---" not in result

    def test_shallow_no_multi_path_marker(self, service: BusinessMapService) -> None:
        """单路径无多路径标记"""
        result: str = service.assemble_slice(["project_saving"])
        assert "多路径" not in result

    def test_shallow_section_count(self, service: BusinessMapService) -> None:
        """浅定位有 2 个 ### 段落（root + project_saving）"""
        result: str = service.assemble_slice(["project_saving"])
        section_count: int = result.count("### ")
        assert section_count == 2


# ── assemble_slice 深定位测试（section 10.3）──


class TestAssembleSliceDeep:
    """深定位：node_ids=["fuzzy_intent"]，路径 root → project_saving → confirm_project → fuzzy_intent，深度 3。"""

    def test_deep_header(self, service: BusinessMapService) -> None:
        """头部显示定位深度 3"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：3"

    def test_deep_contains_all_ancestors(self, service: BusinessMapService) -> None:
        """包含路径上所有节点"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        assert "### 养车预订业务地图" in result
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 确认养车项目" in result
        assert "### 模糊意图场景" in result

    def test_deep_section_count(self, service: BusinessMapService) -> None:
        """深定位有 4 个 ### 段落"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        section_count: int = result.count("### ")
        assert section_count == 4

    def test_deep_fuzzy_intent_content(self, service: BusinessMapService) -> None:
        """fuzzy_intent 节点的完整业务内容"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        assert "车主没有直接说项目名称" in result
        assert "依赖：" in result
        assert "- 车型信息" in result
        assert "待办：" in result
        assert "- 结合里程和保养间隔推荐项目" in result
        assert "产出：" in result
        assert "- 推荐的养车项目" in result
        assert "取消走向：" in result
        assert "- 车主仍然不确定 → 建议车主到店检查，提供商户推荐" in result

    def test_deep_confirm_project_content(self, service: BusinessMapService) -> None:
        """confirm_project 节点的业务内容"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        assert "把车主的表述匹配到具体的养车项目。" in result
        assert "- 识别车主描述对应的项目类型" in result
        assert "- 已确认的养车项目名称" in result
        assert "- 车主不确定要做什么 → 引导到 fuzzy_intent 场景" in result

    def test_deep_no_separator(self, service: BusinessMapService) -> None:
        """单路径无 --- 分隔符"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        assert "---" not in result

    def test_deep_sections_ordered(self, service: BusinessMapService) -> None:
        """各段落按从根到叶的顺序排列"""
        result: str = service.assemble_slice(["fuzzy_intent"])
        pos_root: int = result.index("### 养车预订业务地图")
        pos_ps: int = result.index("### 沟通项目需求与省钱方案")
        pos_cp: int = result.index("### 确认养车项目")
        pos_fi: int = result.index("### 模糊意图场景")
        assert pos_root < pos_ps < pos_cp < pos_fi


# ── assemble_slice 多路径测试（section 10.4）──


class TestAssembleSliceMultiPath:
    """多路径：node_ids=["project_saving", "merchant_search"]，深度 1（多路径）。"""

    def test_multi_path_header(self, service: BusinessMapService) -> None:
        """头部显示定位深度 1（多路径）"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：1（多路径）"

    def test_multi_path_root_appears_once(self, service: BusinessMapService) -> None:
        """根节点只出现一次（去重）"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        root_count: int = result.count("### 养车预订业务地图")
        assert root_count == 1

    def test_multi_path_contains_both_branches(self, service: BusinessMapService) -> None:
        """包含两个分支的内容"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 筛选匹配商户" in result

    def test_multi_path_has_separator(self, service: BusinessMapService) -> None:
        """多路径之间有 --- 分隔符"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        assert "\n\n---\n\n" in result

    def test_multi_path_separator_position(self, service: BusinessMapService) -> None:
        """--- 在第一条路径之后、第二条路径之前"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        pos_ps: int = result.index("### 沟通项目需求与省钱方案")
        pos_sep: int = result.index("---")
        pos_ms: int = result.index("### 筛选匹配商户")
        assert pos_ps < pos_sep < pos_ms

    def test_multi_path_section_count(self, service: BusinessMapService) -> None:
        """多路径有 3 个 ### 段落（root + project_saving + merchant_search）"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        section_count: int = result.count("### ")
        assert section_count == 3

    def test_multi_path_merchant_search_content(self, service: BusinessMapService) -> None:
        """merchant_search 节点的业务内容"""
        result: str = service.assemble_slice(["project_saving", "merchant_search"])
        assert "根据车主的项目需求和偏好" in result
        assert "依赖：" in result
        assert "- 已确认的养车项目（confirm_project 的 output）" in result


# ── 无效 ID 跳过测试 ──


class TestAssembleSliceInvalidId:
    """无效 ID 被忽略，不影响有效路径的组装。"""

    def test_invalid_id_ignored(self, service: BusinessMapService) -> None:
        """含无效 ID 的列表仍能正常输出有效节点"""
        result: str = service.assemble_slice(
            ["not_a_real_node", "project_saving"]
        )
        assert "定位深度：1" in result
        assert "### 沟通项目需求与省钱方案" in result

    def test_all_invalid_returns_empty(self, service: BusinessMapService) -> None:
        """全部无效 ID 返回空字符串"""
        result: str = service.assemble_slice(["fake_a", "fake_b"])
        assert result == ""

    def test_invalid_id_does_not_add_separator(self, service: BusinessMapService) -> None:
        """无效 ID 被过滤后不影响分隔符逻辑"""
        result: str = service.assemble_slice(
            ["not_real", "project_saving"]
        )
        assert "---" not in result
        assert "多路径" not in result


# ── 祖先-后代去重测试 ──


class TestAssembleSliceDedup:
    """祖先-后代去重：同一条路径上的节点只输出一次。"""

    def test_ancestor_descendant_dedup(self, service: BusinessMapService) -> None:
        """同时传入 project_saving 和 fuzzy_intent，project_saving 只输出一次"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        ps_count: int = result.count("### 沟通项目需求与省钱方案")
        assert ps_count == 1

    def test_ancestor_descendant_root_dedup(self, service: BusinessMapService) -> None:
        """祖先-后代去重时根节点也只出现一次"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        root_count: int = result.count("### 养车预订业务地图")
        assert root_count == 1

    def test_ancestor_descendant_depth_is_max(self, service: BusinessMapService) -> None:
        """深度取最大值（fuzzy_intent 深度 3）"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：3（多路径）"

    def test_ancestor_descendant_has_separator(self, service: BusinessMapService) -> None:
        """两条路径之间有 --- 分隔符"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        assert "---" in result

    def test_ancestor_descendant_all_nodes_present(self, service: BusinessMapService) -> None:
        """所有路径节点都出现"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        assert "### 养车预订业务地图" in result
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 确认养车项目" in result
        assert "### 模糊意图场景" in result


# ── 空列表测试 ──


class TestAssembleSliceEmpty:
    """空列表返回空字符串。"""

    def test_empty_list_returns_empty(self, service: BusinessMapService) -> None:
        """空列表输入返回空字符串"""
        result: str = service.assemble_slice([])
        assert result == ""


# ── 单个根节点测试 ──


class TestAssembleSliceRootOnly:
    """单个根节点：node_ids=["root"]，深度 0。"""

    def test_root_only_header(self, service: BusinessMapService) -> None:
        """头部显示定位深度 0"""
        result: str = service.assemble_slice(["root"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：0"

    def test_root_only_content(self, service: BusinessMapService) -> None:
        """只包含根节点内容"""
        result: str = service.assemble_slice(["root"])
        assert "### 养车预订业务地图" in result
        assert "帮助车主完成从需求沟通到预订执行的完整流程。" in result

    def test_root_only_section_count(self, service: BusinessMapService) -> None:
        """只有 1 个 ### 段落"""
        result: str = service.assemble_slice(["root"])
        section_count: int = result.count("### ")
        assert section_count == 1

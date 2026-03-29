"""BusinessMap 端到端测试（Phase 5）。

覆盖场景：
1. StateTreeService 生命周期（读/写/覆盖/不存在）
2. _compress_state_tree 状态树压缩
3. _parse_node_ids 节点 ID 解析
4. 渐进下钻 assemble_slice 集成（navigator7.md §11）
5. 多路径组装与去重
6. HlscContextFormatter + BusinessMapPreprocessor 集成
7. 性能基准（加载 + 组装耗时）
8. read_business_node 工具测试
9. update_state_tree 工具测试
10. BusinessMapPreprocessor 钩子测试
"""

from __future__ import annotations

import asyncio
import contextvars
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hlsc.business_map.loader import BusinessMap
from hlsc.business_map.model import BusinessNode
from hlsc.services.business_map_service import BusinessMapService
from hlsc.services.state_tree_service import StateTreeService

# ── 路径解析 ──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"
_MAINAGENT_SRC: Path = _PROJECT_ROOT / "mainagent"

# 将 mainagent 加入 sys.path，以便导入 business_map_hook 中的工具函数
if str(_MAINAGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_MAINAGENT_SRC))

from src.business_map_hook import (  # noqa: E402
    BusinessMapPreprocessor,
    _INTENT_KEYWORDS,
    _compress_state_tree,
    _current_session_var,
    _parse_node_ids,
)
from src.hlsc_context import (  # noqa: E402
    HlscContextFormatter,
    HlscRequestContext,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(scope="module")
def service() -> BusinessMapService:
    """创建并加载 BusinessMapService（模块级复用）。"""
    svc: BusinessMapService = BusinessMapService()
    svc.load(_BUSINESS_MAP_DIR)
    return svc


# ======================================================================
# 1. StateTreeService 生命周期
# ======================================================================


class TestStateTreeServiceLifecycle:
    """状态树服务的读、写、覆盖、不存在场景。"""

    def test_write_then_read(self, tmp_path: Path) -> None:
        """写入状态树 → 读回 → 内容一致"""
        svc: StateTreeService = StateTreeService()
        content: str = (
            "- [进行中] 沟通项目需求与省钱方案 ← 当前\n"
            "- [ ] 筛选匹配商户\n"
            "- [ ] 执行预订\n"
        )
        svc.write(tmp_path, content)
        result: str | None = svc.read(tmp_path)
        assert result is not None
        assert result == content

    def test_read_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """读取不存在的状态树返回 None"""
        svc: StateTreeService = StateTreeService()
        result: str | None = svc.read(tmp_path)
        assert result is None

    def test_overwrite_returns_updated(self, tmp_path: Path) -> None:
        """覆盖写入后读到新内容"""
        svc: StateTreeService = StateTreeService()
        original: str = "- [ ] 沟通项目需求与省钱方案\n"
        svc.write(tmp_path, original)

        updated: str = (
            "- [完成] 沟通项目需求与省钱方案 → 小保养\n"
            "- [进行中] 筛选匹配商户 ← 当前\n"
            "- [ ] 执行预订\n"
        )
        svc.write(tmp_path, updated)

        result: str | None = svc.read(tmp_path)
        assert result is not None
        assert result == updated
        assert "完成" in result
        assert "进行中" in result

    def test_read_empty_content_returns_none(self, tmp_path: Path) -> None:
        """写入空白内容后读取返回 None"""
        svc: StateTreeService = StateTreeService()
        file_path: Path = tmp_path / StateTreeService.FILENAME
        file_path.write_text("   \n  \n", encoding="utf-8")
        result: str | None = svc.read(tmp_path)
        assert result is None


# ======================================================================
# 2. _compress_state_tree 状态树压缩
# ======================================================================


class TestCompressStateTree:
    """状态树压缩为自然语言简报。"""

    def test_full_state_tree(self) -> None:
        """包含 [完成]、[跳过]、[进行中]、← 当前 的完整状态树"""
        state_tree: str = (
            "- [完成] 沟通项目需求与省钱方案 → 小保养\n"
            "- [跳过] 特殊需求确认\n"
            "- [进行中] 筛选匹配商户\n"
            "  - [进行中] 搜索商户 ← 当前\n"
            "- [ ] 执行预订\n"
        )
        briefing: str = _compress_state_tree(state_tree)
        # 已完成部分
        assert "已完成" in briefing
        assert "沟通项目需求与省钱方案 → 小保养" in briefing
        # 跳过部分也在已完成列表中
        assert "特殊需求确认" in briefing
        assert "已跳过" in briefing
        # 当前在做
        assert "当前在做" in briefing
        assert "筛选匹配商户" in briefing
        assert "搜索商户" in briefing

    def test_empty_state_tree(self) -> None:
        """空状态树 → 空简报"""
        briefing: str = _compress_state_tree("")
        assert briefing == ""

    def test_only_completed_items(self) -> None:
        """全部完成的状态树 → 无"当前在做"部分"""
        state_tree: str = (
            "- [完成] 沟通项目需求与省钱方案 → 小保养\n"
            "- [完成] 筛选匹配商户 → 张三汽修\n"
            "- [完成] 执行预订 → 已预订\n"
        )
        briefing: str = _compress_state_tree(state_tree)
        assert "已完成" in briefing
        assert "当前在做" not in briefing

    def test_only_pending_items(self) -> None:
        """全部未开始 → 空简报（不包含未开始节点）"""
        state_tree: str = (
            "- [ ] 沟通项目需求与省钱方案\n"
            "- [ ] 筛选匹配商户\n"
            "- [ ] 执行预订\n"
        )
        briefing: str = _compress_state_tree(state_tree)
        assert briefing == ""

    def test_current_path_concatenation(self) -> None:
        """← 当前 和 [进行中] 的路径用 → 串联"""
        state_tree: str = (
            "- [进行中] 沟通项目需求与省钱方案\n"
            "  - [进行中] 确认养车项目\n"
            "    - [进行中] 模糊意图场景 ← 当前\n"
        )
        briefing: str = _compress_state_tree(state_tree)
        assert "当前在做" in briefing
        # 路径用 → 连接（无空格）
        assert "沟通项目需求与省钱方案" in briefing
        assert "确认养车项目" in briefing
        assert "模糊意图场景" in briefing

    def test_whitespace_only_lines_ignored(self) -> None:
        """空白行不影响解析"""
        state_tree: str = (
            "\n"
            "- [完成] 任务A\n"
            "\n"
            "- [进行中] 任务B ← 当前\n"
            "\n"
        )
        briefing: str = _compress_state_tree(state_tree)
        assert "任务A" in briefing
        assert "任务B" in briefing


# ======================================================================
# 3. _parse_node_ids 节点 ID 解析
# ======================================================================


class TestParseNodeIds:
    """解析逗号分隔的节点 ID 字符串。"""

    def test_single_id(self) -> None:
        """单个 ID"""
        result: list[str] = _parse_node_ids("project_saving")
        assert result == ["project_saving"]

    def test_multiple_ids(self) -> None:
        """多个 ID 逗号分隔"""
        result: list[str] = _parse_node_ids("project_saving, merchant_search")
        assert result == ["project_saving", "merchant_search"]

    def test_empty_string(self) -> None:
        """空字符串 → 空列表"""
        result: list[str] = _parse_node_ids("")
        assert result == []

    def test_whitespace_handling(self) -> None:
        """前后空白被清理"""
        result: list[str] = _parse_node_ids(" project_saving , fuzzy_intent ")
        assert result == ["project_saving", "fuzzy_intent"]

    def test_none_input(self) -> None:
        """None 输入不报错，返回空列表"""
        # _parse_node_ids 检查 not raw，None 被当作 falsy
        result: list[str] = _parse_node_ids(None)  # type: ignore[arg-type]
        assert result == []

    def test_whitespace_only(self) -> None:
        """纯空白字符串 → 空列表"""
        result: list[str] = _parse_node_ids("   ")
        assert result == []

    def test_trailing_comma(self) -> None:
        """末尾逗号不产生空元素"""
        result: list[str] = _parse_node_ids("project_saving,")
        assert result == ["project_saving"]

    def test_three_ids(self) -> None:
        """三个 ID"""
        result: list[str] = _parse_node_ids("a, b, c")
        assert result == ["a", "b", "c"]


# ======================================================================
# 4. 渐进下钻 assemble_slice 集成（navigator7.md §11）
# ======================================================================


class TestProgressiveDrillDown:
    """模拟 navigator7.md §11 的渐进下钻场景。"""

    def test_round1_shallow_positioning(self, service: BusinessMapService) -> None:
        """第 1 轮：用户说"我想做个保养"，定位到 project_saving（深度 1）

        BusinessMapAgent 只命中 project_saving，输出根 + 第 1 层。
        """
        result: str = service.assemble_slice(["project_saving"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：1"
        # 包含根节点
        assert "### 养车预订业务地图" in result
        # 包含目标节点
        assert "### 沟通项目需求与省钱方案" in result
        # 有 checklist 可供 MainAgent 引导补充信息
        assert "待办：" in result
        assert "确认车主的养车项目" in result

    def test_round2_deep_drilldown(self, service: BusinessMapService) -> None:
        """第 2 轮：用户补充车型和里程，下钻到 fuzzy_intent（深度 3）

        BusinessMapAgent 基于新信息下钻到 confirm_project → fuzzy_intent。
        """
        result: str = service.assemble_slice(["fuzzy_intent"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：3"
        # 完整路径：root → project_saving → confirm_project → fuzzy_intent
        assert "### 养车预订业务地图" in result
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 确认养车项目" in result
        assert "### 模糊意图场景" in result
        # fuzzy_intent 包含"结合里程和保养间隔推荐项目"的指引
        assert "结合里程和保养间隔推荐项目" in result

    def test_round3_branch_switch(self, service: BusinessMapService) -> None:
        """第 3 轮：用户说"帮我找个附近的店"，切换到 merchant_search 分支（深度 1）

        项目已确认，意图转向商户搜索。
        """
        result: str = service.assemble_slice(["merchant_search"])
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：1"
        # 包含 merchant_search 分支内容
        assert "### 筛选匹配商户" in result
        # merchant_search 的依赖标明需要 confirm_project 的产出
        assert "依赖：" in result

    def test_progressive_depth_increases(self, service: BusinessMapService) -> None:
        """渐进收敛：每轮切片的深度递增（1 → 3 → 1 是因为分支切换）"""
        r1: str = service.assemble_slice(["project_saving"])
        r2: str = service.assemble_slice(["fuzzy_intent"])
        r3: str = service.assemble_slice(["merchant_search"])
        depth1: str = r1.split("\n")[0]
        depth2: str = r2.split("\n")[0]
        depth3: str = r3.split("\n")[0]
        assert depth1 == "定位深度：1"
        assert depth2 == "定位深度：3"
        assert depth3 == "定位深度：1"


# ======================================================================
# 5. 多路径组装与去重
# ======================================================================


class TestMultiPathAssembly:
    """多路径组装：同时传入多个 node_id，根节点去重。"""

    def test_two_branch_multi_path(self, service: BusinessMapService) -> None:
        """project_saving + merchant_search：两条路径，根只出现一次"""
        result: str = service.assemble_slice(
            ["project_saving", "merchant_search"]
        )
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：1（多路径）"
        # 根节点去重
        root_count: int = result.count("### 养车预订业务地图")
        assert root_count == 1
        # 两个分支都在
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 筛选匹配商户" in result
        # 有分隔符
        assert "---" in result

    def test_ancestor_descendant_dedup(self, service: BusinessMapService) -> None:
        """project_saving + fuzzy_intent：祖先-后代路径，祖先节点不重复输出"""
        result: str = service.assemble_slice(
            ["project_saving", "fuzzy_intent"]
        )
        ps_count: int = result.count("### 沟通项目需求与省钱方案")
        assert ps_count == 1
        root_count: int = result.count("### 养车预订业务地图")
        assert root_count == 1
        # 深度取最大值
        first_line: str = result.split("\n")[0]
        assert first_line == "定位深度：3（多路径）"

    def test_three_branch_multi_path(self, service: BusinessMapService) -> None:
        """三个一级节点同时命中"""
        result: str = service.assemble_slice(
            ["project_saving", "merchant_search", "booking"]
        )
        assert "多路径" in result.split("\n")[0]
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 筛选匹配商户" in result
        assert "### 执行预订" in result
        # 根节点仍只出现一次
        assert result.count("### 养车预订业务地图") == 1

    def test_cross_branch_deep_multi_path(self, service: BusinessMapService) -> None:
        """跨分支深定位：fuzzy_intent（深度 3）+ search（深度 2）"""
        result: str = service.assemble_slice(["fuzzy_intent", "search"])
        first_line: str = result.split("\n")[0]
        # 深度取最大值 3
        assert "定位深度：3" in first_line
        assert "多路径" in first_line
        # 两条路径的内容都在
        assert "### 模糊意图场景" in result
        # search 在 merchant_search 下
        assert "### 筛选匹配商户" in result


# ======================================================================
# 6. HlscContextFormatter + BusinessMapPreprocessor 集成
# ======================================================================


class TestHlscContextFormatterWithPreprocessor:
    """验证 HlscContextFormatter 注入业务地图切片和状态树。"""

    def test_format_includes_slice_and_state_tree(self) -> None:
        """设置 slice 和 state_tree 后，format() 输出包含对应段落"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        session_id: str = "test_session_001"

        # 手动注入 slice 和 state_tree（模拟 hook 执行后的状态）
        preprocessor._slices[session_id] = (
            "定位深度：1\n\n### 养车预订业务地图\n..."
        )
        preprocessor._state_trees[session_id] = (
            "- [进行中] 沟通项目需求 ← 当前\n- [ ] 筛选商户\n"
        )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        _current_session_var.set(session_id)

        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 验证包含 [business_map_slice] 段落
        assert "[business_map_slice]" in result
        assert "定位深度：1" in result
        # 验证包含 [state_tree] 段落
        assert "[state_tree]" in result
        assert "沟通项目需求" in result

    def test_format_without_preprocessor_backward_compatible(self) -> None:
        """不设置 preprocessor 时，format() 仍正常工作（向后兼容）"""
        formatter: HlscContextFormatter = HlscContextFormatter()
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)
        assert "[request_context]" in result
        assert "current_car: (未设置)" in result
        assert "current_location: (未设置)" in result
        # 不应有业务地图相关内容
        assert "[business_map_slice]" not in result
        assert "[state_tree]" not in result

    def test_format_with_preprocessor_no_data(self) -> None:
        """有 preprocessor 但没有该 session 的数据时，不注入切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        _current_session_var.set("nonexistent_session")

        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)
        assert "[request_context]" in result
        assert "[business_map_slice]" not in result
        assert "[state_tree]" not in result

    def test_format_only_slice_no_state_tree(self) -> None:
        """只有切片没有状态树：只注入 [business_map_slice]"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        session_id: str = "session_slice_only"
        preprocessor._slices[session_id] = "定位深度：2\n\n### 测试节点"

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        _current_session_var.set(session_id)

        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)
        assert "[business_map_slice]" in result
        assert "[state_tree]" not in result

    def test_format_only_state_tree_no_slice(self) -> None:
        """只有状态树没有切片：只注入 [state_tree]"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        session_id: str = "session_tree_only"
        preprocessor._state_trees[session_id] = (
            "- [完成] 任务A\n- [ ] 任务B\n"
        )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        _current_session_var.set(session_id)

        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)
        assert "[business_map_slice]" not in result
        assert "[state_tree]" in result
        assert "任务A" in result


# ======================================================================
# 7. 性能基准
# ======================================================================


class TestPerformance:
    """性能基准：确保关键操作在可接受时间内完成。"""

    def test_business_map_load_under_1_second(self) -> None:
        """BusinessMap.load() 加载示例业务树 < 1 秒"""
        start: float = time.perf_counter()
        _bm: BusinessMap = BusinessMap.load(_BUSINESS_MAP_DIR)
        elapsed: float = time.perf_counter() - start
        assert elapsed < 1.0, f"加载耗时 {elapsed:.3f}s，超过 1 秒上限"

    def test_assemble_slice_5_node_under_100ms(
        self, service: BusinessMapService
    ) -> None:
        """assemble_slice() 组装 5 节点路径 < 100ms"""
        # fuzzy_intent 路径有 4 个节点，加上 merchant_search 共 5+ 个节点
        node_ids: list[str] = ["fuzzy_intent", "merchant_search"]
        start: float = time.perf_counter()
        _result: str = service.assemble_slice(node_ids)
        elapsed: float = time.perf_counter() - start
        assert elapsed < 0.1, f"组装耗时 {elapsed:.3f}s，超过 100ms 上限"

    def test_assemble_slice_all_branches_under_100ms(
        self, service: BusinessMapService
    ) -> None:
        """assemble_slice() 组装所有一级分支 < 100ms"""
        node_ids: list[str] = [
            "project_saving", "merchant_search", "booking"
        ]
        start: float = time.perf_counter()
        _result: str = service.assemble_slice(node_ids)
        elapsed: float = time.perf_counter() - start
        assert elapsed < 0.1, f"组装耗时 {elapsed:.3f}s，超过 100ms 上限"


# ======================================================================
# 8. read_business_node 工具测试
# ======================================================================


# ── Mock 辅助类 ──


@dataclass
class _MockDeps:
    """模拟 AgentDeps，只保留 tool 需要的字段。"""

    session_id: str = "test_session"
    request_id: str = "test_request"
    user_id: str = "test_user"


class _MockRunContext:
    """模拟 RunContext[AgentDeps]。"""

    def __init__(self, deps: _MockDeps) -> None:
        self.deps: _MockDeps = deps


class TestReadBusinessNodeTool:
    """read_business_node 工具的单元测试。"""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """有效 node_id → 返回节点详情 Markdown"""
        from hlsc.tools.read_business_node import read_business_node

        deps: _MockDeps = _MockDeps()
        ctx: Any = _MockRunContext(deps)

        with patch("hlsc.tools.read_business_node.business_map_service") as mock_svc:
            mock_svc.get_business_node_detail.return_value = "### 测试节点\n内容详情"
            result: str = await read_business_node(ctx, node_id="test_node")

        assert "测试节点" in result
        assert "内容详情" in result
        mock_svc.get_business_node_detail.assert_called_once_with("test_node")

    @pytest.mark.asyncio
    async def test_key_error_invalid_node(self) -> None:
        """无效 node_id → KeyError → 返回"不存在"提示"""
        from hlsc.tools.read_business_node import read_business_node

        deps: _MockDeps = _MockDeps()
        ctx: Any = _MockRunContext(deps)

        with patch("hlsc.tools.read_business_node.business_map_service") as mock_svc:
            mock_svc.get_business_node_detail.side_effect = KeyError("不存在")
            result: str = await read_business_node(ctx, node_id="bad_node")

        assert "不存在" in result
        assert "bad_node" in result

    @pytest.mark.asyncio
    async def test_runtime_error_not_loaded(self) -> None:
        """服务未加载 → RuntimeError → 返回错误提示"""
        from hlsc.tools.read_business_node import read_business_node

        deps: _MockDeps = _MockDeps()
        ctx: Any = _MockRunContext(deps)

        with patch("hlsc.tools.read_business_node.business_map_service") as mock_svc:
            mock_svc.get_business_node_detail.side_effect = RuntimeError("未加载")
            result: str = await read_business_node(ctx, node_id="any_node")

        assert "未加载" in result


# ======================================================================
# 9. update_state_tree 工具测试
# ======================================================================


class TestUpdateStateTreeTool:
    """update_state_tree 工具的单元测试。"""

    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path: Path) -> None:
        """写入内容 → 返回 '状态树已更新'"""
        from hlsc.tools.update_state_tree import update_state_tree

        deps: _MockDeps = _MockDeps(
            session_id="sess_001",
            request_id="req_001",
            user_id="user_001",
        )
        ctx: Any = _MockRunContext(deps)
        content: str = "- [进行中] 沟通项目需求 ← 当前\n- [ ] 筛选商户\n"

        with patch("hlsc.tools.update_state_tree.state_tree_service") as mock_svc:
            result: str = await update_state_tree(ctx, content=content)

        assert result == "状态树已更新"
        mock_svc.write.assert_called_once()
        # 验证 write 的第二个参数是 content
        call_args: Any = mock_svc.write.call_args
        assert call_args[0][1] == content

    @pytest.mark.asyncio
    async def test_session_dir_path(self) -> None:
        """验证 _get_session_dir 计算正确的路径"""
        from hlsc.tools.update_state_tree import _get_session_dir

        deps: _MockDeps = _MockDeps(
            session_id="sess_abc",
            user_id="user_xyz",
        )
        with patch.dict("os.environ", {"INNER_STORAGE_DIR": "/tmp/test_inner"}):
            result: Path = _get_session_dir(deps)  # type: ignore[arg-type]

        expected: Path = Path("/tmp/test_inner") / "user_xyz" / "sessions" / "sess_abc"
        assert result == expected

    @pytest.mark.asyncio
    async def test_session_dir_default(self) -> None:
        """INNER_STORAGE_DIR 未设置时使用默认值"""
        from hlsc.tools.update_state_tree import _get_session_dir
        import os

        deps: _MockDeps = _MockDeps(
            session_id="s1",
            user_id="u1",
        )
        env_val: str | None = os.environ.pop("INNER_STORAGE_DIR", None)
        try:
            result: Path = _get_session_dir(deps)  # type: ignore[arg-type]
        finally:
            if env_val is not None:
                os.environ["INNER_STORAGE_DIR"] = env_val

        assert "data/inner" in str(result)
        assert "u1" in str(result)
        assert "s1" in str(result)


# ======================================================================
# 10. BusinessMapPreprocessor 钩子测试
# ======================================================================


class TestBusinessMapPreprocessorHook:
    """BusinessMapPreprocessor 的核心方法测试。"""

    def test_ensure_loaded_success(self) -> None:
        """ensure_loaded 成功加载后 _loaded=True"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        assert preprocessor._loaded is False

        with patch("src.business_map_hook.business_map_service") as mock_svc:
            mock_svc.load.return_value = None
            preprocessor.ensure_loaded()

        assert preprocessor._loaded is True
        mock_svc.load.assert_called_once()

    def test_ensure_loaded_already_loaded_skips(self) -> None:
        """已加载后再次调用 ensure_loaded 不会重复 load"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with patch("src.business_map_hook.business_map_service") as mock_svc:
            preprocessor.ensure_loaded()

        mock_svc.load.assert_not_called()

    def test_ensure_loaded_failure(self) -> None:
        """ensure_loaded 加载失败后 _loaded 仍为 False"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()

        with patch("src.business_map_hook.business_map_service") as mock_svc:
            mock_svc.load.side_effect = Exception("加载出错")
            preprocessor.ensure_loaded()

        assert preprocessor._loaded is False

    def test_cleanup_session(self) -> None:
        """cleanup_session 清除指定 session 的缓存"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "session_to_clean"
        preprocessor._slices[sid] = "切片内容"
        preprocessor._state_trees[sid] = "状态树内容"

        preprocessor.cleanup_session(sid)

        assert sid not in preprocessor._slices
        assert sid not in preprocessor._state_trees

    def test_cleanup_session_nonexistent(self) -> None:
        """cleanup_session 对不存在的 session 不报错"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        # 不应抛出异常
        preprocessor.cleanup_session("nonexistent_session")

    def test_evict_if_needed_under_limit(self) -> None:
        """缓存未超上限时不做清理"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        i: int
        for i in range(50):
            preprocessor._slices[f"session_{i}"] = f"slice_{i}"
            preprocessor._state_trees[f"session_{i}"] = f"tree_{i}"

        preprocessor._evict_if_needed()
        assert len(preprocessor._slices) == 50

    def test_evict_if_needed_over_limit(self) -> None:
        """缓存超过 100 时清理最早条目"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        i: int
        for i in range(105):
            preprocessor._slices[f"session_{i:03d}"] = f"slice_{i}"
            preprocessor._state_trees[f"session_{i:03d}"] = f"tree_{i}"

        assert len(preprocessor._slices) == 105
        preprocessor._evict_if_needed()
        assert len(preprocessor._slices) == 100
        # 最早的 5 个 session 被清理
        assert "session_000" not in preprocessor._slices
        assert "session_004" not in preprocessor._slices
        # 后面的保留
        assert "session_005" in preprocessor._slices
        assert "session_104" in preprocessor._slices

    @pytest.mark.asyncio
    async def test_call_hook_not_loaded_returns_early(self) -> None:
        """__call__ 中如果 ensure_loaded 失败，直接返回不继续"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()

        with patch("src.business_map_hook.business_map_service") as mock_svc:
            mock_svc.load.side_effect = Exception("加载出错")
            await preprocessor(
                user_id="u1",
                session_id="s1",
                deps=MagicMock(),
                message="你好",
            )

        assert preprocessor._loaded is False
        # 不应有切片
        assert "s1" not in preprocessor._slices

    @pytest.mark.asyncio
    async def test_call_hook_success_with_slice(self) -> None:
        """__call__ 完整流程：读状态树 → 调用 navigator → 组装切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True  # 跳过 ensure_loaded

        state_tree_content: str = "- [进行中] 沟通项目需求 ← 当前\n"
        slice_content: str = "定位深度：1\n\n### 沟通项目需求与省钱方案"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving"],
            ) as mock_nav,
        ):
            mock_tree_svc.read.return_value = state_tree_content
            mock_biz_svc.assemble_slice.return_value = slice_content

            await preprocessor(
                user_id="u1",
                session_id="s1",
                deps=MagicMock(),
                message="我想做保养",
            )

        # 状态树被存储
        assert preprocessor._state_trees["s1"] == state_tree_content
        # 切片被存储
        assert preprocessor._slices["s1"] == slice_content
        # navigator 被调用
        mock_nav.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_hook_navigator_returns_empty(self) -> None:
        """navigator 返回空列表 → 不组装切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_tree_svc.read.return_value = None

            await preprocessor(
                user_id="u1",
                session_id="s2",
                deps=MagicMock(),
                message="你好",
            )

        assert "s2" not in preprocessor._slices
        mock_biz_svc.assemble_slice.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_hook_no_state_tree(self) -> None:
        """没有状态树文件时 → state_trees 中不存储该 session"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = "定位深度：1\n\n### 节点"

            await preprocessor(
                user_id="u1",
                session_id="s3",
                deps=MagicMock(),
                message="做保养",
            )

        assert "s3" not in preprocessor._state_trees
        assert "s3" in preprocessor._slices

    @pytest.mark.asyncio
    async def test_call_hook_assemble_exception(self) -> None:
        """assemble_slice 异常 → 不崩溃，切片不存储"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.side_effect = RuntimeError("组装出错")

            # 不应抛异常
            await preprocessor(
                user_id="u1",
                session_id="s4",
                deps=MagicMock(),
                message="做保养",
            )

        assert "s4" not in preprocessor._slices

    @pytest.mark.asyncio
    async def test_call_hook_sets_current_session_id(self) -> None:
        """__call__ 通过 contextvars 设置当前 session_id"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service"),
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_tree_svc.read.return_value = None

            await preprocessor(
                user_id="u1",
                session_id="session_xyz",
                deps=MagicMock(),
                message="你好",
            )

        assert preprocessor.current_session_id == "session_xyz"

    @pytest.mark.asyncio
    async def test_call_hook_eviction_triggered(self) -> None:
        """__call__ 中超过 100 个 session 时触发 eviction"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        # 预填充 101 个 session
        i: int
        for i in range(101):
            preprocessor._slices[f"old_{i:03d}"] = f"slice_{i}"
            preprocessor._state_trees[f"old_{i:03d}"] = f"tree_{i}"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = "切片"

            await preprocessor(
                user_id="u1",
                session_id="new_session",
                deps=MagicMock(),
                message="做保养",
            )

        # eviction 后最早的条目被清理
        assert "old_000" not in preprocessor._slices


# ======================================================================
# 11. Hook 集成测试（Section B）
# ======================================================================


class TestHookIntegration:
    """Hook 级别集成测试：验证 BusinessMapPreprocessor.__call__ 在各种
    subagent 响应场景下的行为。使用 mock 替代 call_subagent / state_tree_service
    / business_map_service。
    """

    @pytest.mark.asyncio
    async def test_successful_node_id_slice_assembled(self) -> None:
        """navigator 返回有效 node_id → 切片被正确组装并缓存"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        expected_slice: str = "定位深度：1\n\n### 沟通项目需求与省钱方案"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = expected_slice

            await preprocessor(
                user_id="u1",
                session_id="hook_ok",
                deps=MagicMock(),
                message="保养",
            )

        # 切片被正确缓存
        assert preprocessor._slices["hook_ok"] == expected_slice
        mock_biz_svc.assemble_slice.assert_called_once_with(["project_saving"])

    @pytest.mark.asyncio
    async def test_multiple_node_ids_multi_path_slice(self) -> None:
        """navigator 返回多个 node_id → assemble_slice 接收完整列表"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        multi_slice: str = "定位深度：1（多路径）\n\n### 节点A\n\n---\n\n### 节点B"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["project_saving", "merchant_search"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = multi_slice

            await preprocessor(
                user_id="u1",
                session_id="hook_multi",
                deps=MagicMock(),
                message="保养和找店",
            )

        assert preprocessor._slices["hook_multi"] == multi_slice
        mock_biz_svc.assemble_slice.assert_called_once_with(
            ["project_saving", "merchant_search"]
        )

    @pytest.mark.asyncio
    async def test_invalid_node_ids_gracefully_ignored(self) -> None:
        """navigator 返回包含无效 ID 的列表 → assemble_slice 返回空 → 不存储切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=["nonexistent_node_xyz"],
            ),
        ):
            mock_tree_svc.read.return_value = None
            # assemble_slice 过滤无效 ID 后返回空字符串
            mock_biz_svc.assemble_slice.return_value = ""

            await preprocessor(
                user_id="u1",
                session_id="hook_invalid",
                deps=MagicMock(),
                message="做个什么",
            )

        # 空切片不应被存储（代码检查 if slice_md:）
        assert "hook_invalid" not in preprocessor._slices

    @pytest.mark.asyncio
    async def test_empty_string_response_no_slice(self) -> None:
        """navigator 返回空字符串 → _parse_node_ids 返回 [] → 不组装切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
                return_value=[],  # _parse_node_ids("") → []
            ),
        ):
            mock_tree_svc.read.return_value = None

            await preprocessor(
                user_id="u1",
                session_id="hook_empty",
                deps=MagicMock(),
                message="你好",
            )

        assert "hook_empty" not in preprocessor._slices
        mock_biz_svc.assemble_slice.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_response_parses_valid_ids_only(self) -> None:
        """navigator 返回含自然语言的文本 → _parse_node_ids 只提取逗号分隔 token

        _parse_node_ids 不做 ID 合法性校验，它只是拆分逗号。
        但 assemble_slice 会跳过不存在的 node_id。
        """
        # 测试 _parse_node_ids 对畸形输入的行为
        malformed: str = "I think it's project_saving"
        result: list[str] = _parse_node_ids(malformed)
        # 没有逗号，整行作为单个 token
        assert result == ["I think it's project_saving"]

        # 逗号分隔的混合内容
        mixed: str = "project_saving, some_garbage, merchant_search"
        result2: list[str] = _parse_node_ids(mixed)
        assert result2 == ["project_saving", "some_garbage", "merchant_search"]

    @pytest.mark.asyncio
    async def test_call_subagent_exception_returns_empty(self) -> None:
        """call_subagent 抛出异常 → _call_navigator 返回空列表，不崩溃"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                new_callable=AsyncMock,
                side_effect=ConnectionError("subagent 不可达"),
            ),
        ):
            mock_tree_svc.read.return_value = None

            # 不应抛异常
            await preprocessor(
                user_id="u1",
                session_id="hook_exc",
                deps=MagicMock(),
                message="保养",
            )

        # 异常后不应有切片
        assert "hook_exc" not in preprocessor._slices
        mock_biz_svc.assemble_slice.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_state_tree_briefing_empty(self) -> None:
        """没有状态树文件 → navigator 收到的 state_tree 为 None → 简报为空"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        captured_kwargs: dict[str, Any] = {}

        async def _capture_navigator(
            message: str,
            state_tree: str | None,
            deps: Any,
        ) -> list[str]:
            captured_kwargs["state_tree"] = state_tree
            return ["project_saving"]

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                side_effect=_capture_navigator,
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = "切片"

            await preprocessor(
                user_id="u1",
                session_id="hook_no_tree",
                deps=MagicMock(),
                message="保养",
            )

        # navigator 收到的 state_tree 应为 None
        assert captured_kwargs["state_tree"] is None
        # state_trees 中不应有该 session
        assert "hook_no_tree" not in preprocessor._state_trees

    @pytest.mark.asyncio
    async def test_existing_state_tree_briefing_contains_completed(self) -> None:
        """有状态树文件 → state_tree 被传给 navigator → 简报包含已完成项"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        state_tree_content: str = (
            "- [完成] 沟通项目需求与省钱方案 → 小保养\n"
            "- [进行中] 筛选匹配商户 ← 当前\n"
            "- [ ] 执行预订\n"
        )

        captured_kwargs: dict[str, Any] = {}

        async def _capture_navigator(
            message: str,
            state_tree: str | None,
            deps: Any,
        ) -> list[str]:
            captured_kwargs["state_tree"] = state_tree
            return ["merchant_search"]

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                side_effect=_capture_navigator,
            ),
        ):
            mock_tree_svc.read.return_value = state_tree_content
            mock_biz_svc.assemble_slice.return_value = "切片"

            await preprocessor(
                user_id="u1",
                session_id="hook_has_tree",
                deps=MagicMock(),
                message="找店",
            )

        # navigator 收到的 state_tree 应包含完整内容
        assert captured_kwargs["state_tree"] == state_tree_content
        # state_trees 中应缓存该 session
        assert preprocessor._state_trees["hook_has_tree"] == state_tree_content

    @pytest.mark.asyncio
    async def test_per_session_cache_no_overwrite(self) -> None:
        """两个不同 session 各自缓存切片，A 的切片不会覆盖 B 的"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        slice_a: str = "切片A - project_saving"
        slice_b: str = "切片B - merchant_search"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                new_callable=AsyncMock,
            ) as mock_nav,
        ):
            mock_tree_svc.read.return_value = None

            # Session A
            mock_nav.return_value = ["project_saving"]
            mock_biz_svc.assemble_slice.return_value = slice_a

            await preprocessor(
                user_id="u1",
                session_id="session_A",
                deps=MagicMock(),
                message="保养",
            )

            # Session B
            mock_nav.return_value = ["merchant_search"]
            mock_biz_svc.assemble_slice.return_value = slice_b

            await preprocessor(
                user_id="u1",
                session_id="session_B",
                deps=MagicMock(),
                message="找店",
            )

        # 两个 session 各自缓存，互不覆盖
        assert preprocessor._slices["session_A"] == slice_a
        assert preprocessor._slices["session_B"] == slice_b


# ======================================================================
# 12. Session 隔离测试（Section C）
# ======================================================================


class TestSessionIsolation:
    """验证两个 session 不会互相泄漏状态。

    关键点：
    - _current_session_var 使用 contextvars.ContextVar，在 asyncio Task 之间隔离
    - preprocessor._slices / _state_trees 按 session_id 索引，各 session 独立
    - HlscContextFormatter 通过 preprocessor.current_session_id 读取当前 session 数据
    """

    @pytest.mark.asyncio
    async def test_interleaved_sessions_no_leak(self) -> None:
        """session A 和 B 交替执行 hook，formatter 仍读到各自的数据"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()

        # 手动注入两个 session 的切片和状态树
        preprocessor._slices["session_A"] = "切片A：沟通项目需求"
        preprocessor._slices["session_B"] = "切片B：筛选商户"
        preprocessor._state_trees["session_A"] = "- [进行中] 任务A ← 当前\n"
        preprocessor._state_trees["session_B"] = "- [完成] 任务B\n"

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        ctx: HlscRequestContext = HlscRequestContext()

        # 切换到 session A → formatter 读到 A 的数据
        _current_session_var.set("session_A")
        result_a: str = formatter.format(ctx)
        assert "切片A：沟通项目需求" in result_a
        assert "任务A" in result_a
        assert "切片B" not in result_a
        assert "任务B" not in result_a

        # 切换到 session B → formatter 读到 B 的数据
        _current_session_var.set("session_B")
        result_b: str = formatter.format(ctx)
        assert "切片B：筛选商户" in result_b
        assert "任务B" in result_b
        assert "切片A" not in result_b
        assert "任务A" not in result_b

        # 再切回 session A → 仍然正确
        _current_session_var.set("session_A")
        result_a2: str = formatter.format(ctx)
        assert "切片A：沟通项目需求" in result_a2
        assert "切片B" not in result_a2

    @pytest.mark.asyncio
    async def test_concurrent_tasks_session_isolation(self) -> None:
        """使用 asyncio.create_task 模拟并发：两个 task 各自设置 session，互不干扰。

        这是 contextvars 安全性的关键测试。
        每个 asyncio.Task 拥有独立的 Context 副本，因此各 task 内的
        _current_session_var 设置不会影响其他 task。
        """
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._slices["sess_concurrent_A"] = "切片并发A"
        preprocessor._slices["sess_concurrent_B"] = "切片并发B"

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )

        results: dict[str, str] = {}
        errors: list[str] = []

        async def task_a() -> None:
            """Task A：设置 session A，等待，验证仍是 A"""
            _current_session_var.set("sess_concurrent_A")
            await asyncio.sleep(0.01)  # 让出控制权，允许 task B 执行
            # 验证 contextvars 隔离：即使 task B 已设置其 session，A 仍看到自己的
            sid: str = _current_session_var.get()
            if sid != "sess_concurrent_A":
                errors.append(f"Task A 期望 sess_concurrent_A，实际 {sid}")
            ctx: HlscRequestContext = HlscRequestContext()
            results["A"] = formatter.format(ctx)

        async def task_b() -> None:
            """Task B：设置 session B，等待，验证仍是 B"""
            _current_session_var.set("sess_concurrent_B")
            await asyncio.sleep(0.01)  # 让出控制权
            sid: str = _current_session_var.get()
            if sid != "sess_concurrent_B":
                errors.append(f"Task B 期望 sess_concurrent_B，实际 {sid}")
            ctx: HlscRequestContext = HlscRequestContext()
            results["B"] = formatter.format(ctx)

        # 使用 asyncio.create_task 创建并发任务
        # create_task 会复制当前 Context，让每个 task 拥有独立的 contextvars 空间
        t_a: asyncio.Task[None] = asyncio.create_task(task_a())
        t_b: asyncio.Task[None] = asyncio.create_task(task_b())
        await asyncio.gather(t_a, t_b)

        # 无错误
        assert errors == [], f"并发隔离失败: {errors}"

        # Task A 只看到 A 的切片
        assert "切片并发A" in results["A"]
        assert "切片并发B" not in results["A"]

        # Task B 只看到 B 的切片
        assert "切片并发B" in results["B"]
        assert "切片并发A" not in results["B"]

    def test_session_a_has_tree_b_does_not(self) -> None:
        """A 有状态树 B 没有，B 不会读到 A 的状态树"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._state_trees["iso_A"] = "- [完成] 任务A\n"
        # session B 没有状态树

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        ctx: HlscRequestContext = HlscRequestContext()

        # A 看到状态树
        _current_session_var.set("iso_A")
        result_a: str = formatter.format(ctx)
        assert "[state_tree]" in result_a
        assert "任务A" in result_a

        # B 看不到 A 的状态树
        _current_session_var.set("iso_B")
        result_b: str = formatter.format(ctx)
        assert "[state_tree]" not in result_b
        assert "任务A" not in result_b

    def test_different_slices_no_cross_read(self) -> None:
        """A 和 B 各有不同切片，formatter 按 session 隔离读取"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._slices["slice_A"] = "A的切片：保养方案"
        preprocessor._slices["slice_B"] = "B的切片：商户搜索"
        preprocessor._state_trees["slice_A"] = "- [进行中] 保养 ← 当前\n"
        preprocessor._state_trees["slice_B"] = "- [完成] 搜索 → 张三店\n"

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        ctx: HlscRequestContext = HlscRequestContext()

        # 验证 A 只看到 A 的数据
        _current_session_var.set("slice_A")
        result_a: str = formatter.format(ctx)
        assert "A的切片：保养方案" in result_a
        assert "保养" in result_a
        assert "B的切片" not in result_a
        assert "张三店" not in result_a

        # 验证 B 只看到 B 的数据
        _current_session_var.set("slice_B")
        result_b: str = formatter.format(ctx)
        assert "B的切片：商户搜索" in result_b
        assert "张三店" in result_b
        assert "A的切片" not in result_b
        assert "保养" not in result_b

    @pytest.mark.asyncio
    async def test_repeated_alternation_multiple_turns(self) -> None:
        """多轮交替：模拟 A/B 交替多轮请求，每轮各自数据正确"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor
        )
        ctx: HlscRequestContext = HlscRequestContext()

        turn: int
        for turn in range(5):
            # 每轮更新切片（模拟 hook 更新缓存）
            preprocessor._slices["alt_A"] = f"A切片_轮{turn}"
            preprocessor._slices["alt_B"] = f"B切片_轮{turn}"

            # A 读取
            _current_session_var.set("alt_A")
            result_a: str = formatter.format(ctx)
            assert f"A切片_轮{turn}" in result_a
            assert f"B切片_轮{turn}" not in result_a

            # B 读取
            _current_session_var.set("alt_B")
            result_b: str = formatter.format(ctx)
            assert f"B切片_轮{turn}" in result_b
            assert f"A切片_轮{turn}" not in result_b

    @pytest.mark.asyncio
    async def test_concurrent_hook_calls_session_data_isolated(self) -> None:
        """并发 hook 调用：两个 session 同时通过 __call__ 写入，各自数据正确"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        async def run_session(
            session_id: str,
            node_id: str,
            slice_content: str,
        ) -> None:
            """模拟单个 session 的 hook 调用"""
            with (
                patch("src.business_map_hook.state_tree_service") as mock_tree,
                patch("src.business_map_hook.business_map_service") as mock_biz,
                patch.object(
                    preprocessor,
                    "_call_navigator",
                    new_callable=AsyncMock,
                    return_value=[node_id],
                ),
            ):
                mock_tree.read.return_value = None
                mock_biz.assemble_slice.return_value = slice_content

                await preprocessor(
                    user_id="u1",
                    session_id=session_id,
                    deps=MagicMock(),
                    message="测试消息",
                )

        # 顺序执行两个 session（因为 mock 的 with 作用域限制，并发需要各自 patch）
        await run_session("conc_A", "project_saving", "并发切片A")
        await run_session("conc_B", "merchant_search", "并发切片B")

        # 各自数据正确，互不覆盖
        assert preprocessor._slices["conc_A"] == "并发切片A"
        assert preprocessor._slices["conc_B"] == "并发切片B"


# ======================================================================
# 13. Hook-through 集成测试
# ======================================================================


class TestHookThroughIntegration:
    """Hook-through 集成测试：真实代码路径，仅 mock A2A 调用。

    验证完整链路：
    hook.__call__() → call_subagent (mocked) → parse_node_ids →
    business_map_service.assemble_slice (real) → preprocessor cache →
    HlscContextFormatter.format (real) → 输出包含正确切片
    """

    @pytest.fixture(autouse=True)
    def _load_real_service(self) -> None:
        """确保模块级 business_map_service 单例已加载真实 YAML。"""
        from hlsc.services.business_map_service import business_map_service

        if not business_map_service.is_loaded:
            business_map_service.load(_BUSINESS_MAP_DIR)

    # ------------------------------------------------------------------
    # Test 1: Full chain — shallow hit
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_shallow_hit(self, tmp_path: Path) -> None:
        """浅层命中：call_subagent 返回 project_saving → 输出包含深度 1 切片"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_shallow"
        session_id: str = "sess_shallow"

        # mock call_subagent 返回 "project_saving"
        mock_subagent: AsyncMock = AsyncMock(return_value="project_saving")

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="我车该保养了",
            )

        # 创建 formatter 并生成输出
        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor,
        )
        _current_session_var.set(session_id)
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 验证输出包含 [business_map_slice] 和正确内容
        assert "[business_map_slice]" in result
        assert "沟通项目需求与省钱方案" in result
        assert "定位深度：1" in result

    # ------------------------------------------------------------------
    # Test 2: Full chain — deep hit
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_deep_hit(self, tmp_path: Path) -> None:
        """深层命中：call_subagent 返回 fuzzy_intent → 深度 3 切片包含 4 个节点"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_deep"
        session_id: str = "sess_deep"

        mock_subagent: AsyncMock = AsyncMock(return_value="fuzzy_intent")

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="我车跑了两万公里了不知道该做什么",
            )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor,
        )
        _current_session_var.set(session_id)
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 验证深度 3 切片包含完整路径上的 4 个节点
        assert "[business_map_slice]" in result
        assert "定位深度：3" in result
        # root → project_saving → confirm_project → fuzzy_intent
        assert "### 养车预订业务地图" in result
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 确认养车项目" in result
        assert "### 模糊意图场景" in result

    # ------------------------------------------------------------------
    # Test 3: Full chain — multi-path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_multi_path(self, tmp_path: Path) -> None:
        """多路径命中：两个 node_id → 输出包含多路径和 --- 分隔符"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_multi"
        session_id: str = "sess_multi"

        mock_subagent: AsyncMock = AsyncMock(
            return_value="project_saving, merchant_search",
        )

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="我想做保养，顺便帮我找个靠谱的店",
            )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor,
        )
        _current_session_var.set(session_id)
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 验证多路径输出
        assert "[business_map_slice]" in result
        assert "多路径" in result
        assert "---" in result
        assert "### 沟通项目需求与省钱方案" in result
        assert "### 筛选匹配商户" in result

    # ------------------------------------------------------------------
    # Test 4: Full chain — with state tree
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_with_state_tree(self, tmp_path: Path) -> None:
        """有状态树时：输出同时包含 [business_map_slice] 和 [state_tree]"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_tree"
        session_id: str = "sess_tree"

        # 创建 state_tree.md 文件
        session_dir: Path = (
            tmp_path / user_id / "sessions" / session_id
        )
        session_dir.mkdir(parents=True, exist_ok=True)
        state_tree_content: str = (
            "- [完成] 沟通项目需求与省钱方案 → 小保养\n"
            "- [进行中] 确认省钱方法 ← 当前\n"
            "- [ ] 筛选匹配商户\n"
            "- [ ] 执行预订\n"
        )
        (session_dir / "state_tree.md").write_text(
            state_tree_content, encoding="utf-8",
        )

        mock_subagent: AsyncMock = AsyncMock(return_value="confirm_saving")

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="有什么省钱的办法吗",
            )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor,
        )
        _current_session_var.set(session_id)
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 验证同时包含切片和状态树
        assert "[business_map_slice]" in result
        assert "### 确认省钱方法" in result
        assert "[state_tree]" in result
        assert "沟通项目需求与省钱方案" in result

    # ------------------------------------------------------------------
    # Test 5: Full chain — navigator failure graceful degradation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_navigator_failure(self, tmp_path: Path) -> None:
        """navigator 失败时优雅降级：无切片但 MainAgent 上下文仍正常"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_fail"
        session_id: str = "sess_fail"

        # call_subagent 抛出 ConnectionError
        mock_subagent: AsyncMock = AsyncMock(
            side_effect=ConnectionError("subagent 不可达"),
        )

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            # 不应抛异常
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="我想做保养",
            )

        formatter: HlscContextFormatter = HlscContextFormatter(
            preprocessor=preprocessor,
        )
        _current_session_var.set(session_id)
        ctx: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(ctx)

        # 不应包含切片（navigator 失败）
        assert "[business_map_slice]" not in result
        # MainAgent 基础上下文仍正常（car/location 信息）
        assert "[request_context]" in result
        assert "current_car" in result
        assert "current_location" in result

    # ------------------------------------------------------------------
    # Test 6: Full chain — skip filter for short messages
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_chain_skip_filter_short_message(
        self, tmp_path: Path,
    ) -> None:
        """短消息过滤：有缓存时，闲聊/确认类短消息不触发 navigator 调用（R3 规则）"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        user_id: str = "user_skip"
        session_id: str = "sess_skip"

        # 预填充缓存切片和导航快照，使 R1/R2 不触发
        preprocessor._slices[session_id] = "已有切片"
        preprocessor._nav_state_trees[session_id] = None  # 匹配无状态树的情况

        mock_subagent: AsyncMock = AsyncMock(return_value="project_saving")

        with (
            patch(
                "agent_sdk.a2a.call_subagent.call_subagent",
                mock_subagent,
            ),
            patch.dict(
                "os.environ",
                {"INNER_STORAGE_DIR": str(tmp_path)},
            ),
        ):
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="好的",
            )

        # call_subagent 不应被调用（被 _should_navigate R3 规则过滤）
        mock_subagent.assert_not_awaited()
        # 缓存切片保持不变
        assert preprocessor._slices[session_id] == "已有切片"


# ======================================================================
# 14. Navigator 调用策略测试（_should_navigate 混合策略）
# ======================================================================


class TestNavigationCallStrategy:
    """测试 BusinessMapPreprocessor._should_navigate 混合策略。

    规则：
    - R1: 无缓存切片 → 必须调用（首次请求）
    - R2: 状态树变化 → 必须调用
    - R3: 短消息（<=8 字符）且无意图关键词 → 跳过
    - R4: 包含意图跳转关键词 → 必须调用
    - R5: 其他长消息 → 调用（默认宁可多调）
    """

    # ------------------------------------------------------------------
    # R1: 首次请求测试
    # ------------------------------------------------------------------

    def test_r1_no_cache_must_call(self) -> None:
        """无缓存切片时必须调用"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        # _slices 为空 → 该 session 无缓存
        result: bool = preprocessor._should_navigate(
            session_id="new_session",
            message="你好",
            current_state_tree=None,
        )
        assert result is True

    def test_r1_has_cache_not_first(self) -> None:
        """有缓存时不再是首次"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "cached_session"
        preprocessor._slices[sid] = "some slice"
        preprocessor._nav_state_trees[sid] = None
        # 状态树匹配（都是 None），短消息无关键词 → R3 命中，跳过
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="好",
            current_state_tree=None,
        )
        assert result is False

    # ------------------------------------------------------------------
    # R2: 状态树变化测试
    # ------------------------------------------------------------------

    def test_r2_state_tree_changed_must_call(self) -> None:
        """状态树变化后必须调用"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "tree_change_session"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = "old state"
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="好",
            current_state_tree="new state",
        )
        assert result is True

    def test_r2_state_tree_unchanged_skip(self) -> None:
        """状态树未变化时跳过（配合短消息无关键词）"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "tree_same_session"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = "same state"
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="好",
            current_state_tree="same state",
        )
        assert result is False

    def test_r2_state_tree_from_none_to_some(self) -> None:
        """状态树从无到有必须调用"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "tree_none_to_some"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="好的",
            current_state_tree="- [进行中] 沟通项目需求 ← 当前\n",
        )
        assert result is True

    # ------------------------------------------------------------------
    # R3: 短消息跳过测试
    # ------------------------------------------------------------------

    def test_r3_short_greeting_skip(self) -> None:
        """短问候跳过：'好的'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r3_greeting"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="好的",
            current_state_tree=None,
        )
        assert result is False

    def test_r3_short_data_reply_skip(self) -> None:
        """短数据回复跳过：'凯美瑞'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r3_data"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        # "凯美瑞" 3 个字符，不含意图关键词 → 跳过
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="凯美瑞",
            current_state_tree=None,
        )
        assert result is False

    def test_r3_short_with_keyword_still_calls(self) -> None:
        """短消息含关键词仍调用：'换机油'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r3_keyword"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        # "换机油" 3 个字符但包含 "换" → R3 不跳过 → R4 命中 → 调用
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="换机油",
            current_state_tree=None,
        )
        assert result is True

    # ------------------------------------------------------------------
    # R4: 意图关键词测试
    # ------------------------------------------------------------------

    def test_r4_merchant_keyword_calls(self) -> None:
        """商户关键词触发：'帮我找个附近的店'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r4_merchant"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="帮我找个附近的店",
            current_state_tree=None,
        )
        assert result is True

    def test_r4_booking_keyword_calls(self) -> None:
        """预订关键词触发：'帮我预约一下'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r4_booking"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="帮我预约一下",
            current_state_tree=None,
        )
        assert result is True

    def test_r4_intent_change_keyword_calls(self) -> None:
        """意图改变关键词触发：'算了不做了'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r4_change"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="算了不做了",
            current_state_tree=None,
        )
        assert result is True

    def test_r4_saving_keyword_calls(self) -> None:
        """省钱关键词触发：'有没有什么优惠'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r4_saving"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="有没有什么优惠",
            current_state_tree=None,
        )
        assert result is True

    # ------------------------------------------------------------------
    # R5: 长消息默认调用测试
    # ------------------------------------------------------------------

    def test_r5_long_message_without_keywords_calls(self) -> None:
        """长消息无关键词也调用：'我上次在那家店做的感觉还行吧'"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        sid: str = "r5_long"
        preprocessor._slices[sid] = "cached slice"
        preprocessor._nav_state_trees[sid] = None
        # 16 个字符，超过 8 字符阈值，无意图关键词 → R5 默认调用
        result: bool = preprocessor._should_navigate(
            session_id=sid,
            message="我上次在那家店做的感觉还行吧",
            current_state_tree=None,
        )
        assert result is True

    # ------------------------------------------------------------------
    # 集成测试：完整 __call__ 流程中的 _should_navigate 效果
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_flow_first_request_calls_navigator(self) -> None:
        """首次请求调用 Navigator"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        mock_nav: AsyncMock = AsyncMock(return_value=["project_saving"])
        slice_content: str = "定位深度：1\n\n### 沟通项目需求与省钱方案"

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                mock_nav,
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = slice_content

            await preprocessor(
                user_id="u1",
                session_id="first_req",
                deps=MagicMock(),
                message="我想做保养",
            )

        # 首次请求（R1），navigator 应被调用
        mock_nav.assert_awaited_once()
        assert preprocessor._slices["first_req"] == slice_content

    @pytest.mark.asyncio
    async def test_full_flow_cached_short_reply_skips(self) -> None:
        """有缓存+短回复跳过 Navigator"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        slice_content: str = "定位深度：1\n\n### 沟通项目需求与省钱方案"
        call_count: int = 0

        async def counting_navigator(
            message: str,
            state_tree: str | None,
            deps: Any,
        ) -> list[str]:
            nonlocal call_count
            call_count += 1
            return ["project_saving"]

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                side_effect=counting_navigator,
            ),
        ):
            mock_tree_svc.read.return_value = None
            mock_biz_svc.assemble_slice.return_value = slice_content

            # 第一次调用：首次请求，navigator 应被调用
            await preprocessor(
                user_id="u1",
                session_id="cached_skip",
                deps=MagicMock(),
                message="我想做保养",
            )
            assert call_count == 1

            # 第二次调用：有缓存 + 短消息无关键词 → 跳过
            await preprocessor(
                user_id="u1",
                session_id="cached_skip",
                deps=MagicMock(),
                message="好的",
            )
            # navigator 不应再被调用（仍然只有 1 次）
            assert call_count == 1

        # 缓存切片仍然存在
        assert preprocessor._slices["cached_skip"] == slice_content

    @pytest.mark.asyncio
    async def test_full_flow_cached_keyword_message_calls(self) -> None:
        """有缓存但含关键词仍调用"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        slice_v1: str = "切片v1"
        slice_v2: str = "切片v2"
        call_count: int = 0

        async def counting_navigator(
            message: str,
            state_tree: str | None,
            deps: Any,
        ) -> list[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ["project_saving"]
            return ["merchant_search"]

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                side_effect=counting_navigator,
            ),
        ):
            mock_tree_svc.read.return_value = None

            # 第一次调用：首次请求
            mock_biz_svc.assemble_slice.return_value = slice_v1
            await preprocessor(
                user_id="u1",
                session_id="cached_kw",
                deps=MagicMock(),
                message="我想做保养",
            )
            assert call_count == 1

            # 第二次调用：有缓存但消息含 "附近" 关键词 → R4 命中 → 调用
            mock_biz_svc.assemble_slice.return_value = slice_v2
            await preprocessor(
                user_id="u1",
                session_id="cached_kw",
                deps=MagicMock(),
                message="帮我找附近的店",
            )
            assert call_count == 2

        # 切片应被更新为 v2
        assert preprocessor._slices["cached_kw"] == slice_v2

    @pytest.mark.asyncio
    async def test_full_flow_state_tree_change_triggers_call(
        self, tmp_path: Path,
    ) -> None:
        """状态树变化触发重新调用"""
        preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()
        preprocessor._loaded = True

        user_id: str = "u1"
        session_id: str = "tree_change"
        session_dir: Path = tmp_path / user_id / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        state_tree_v1: str = "- [进行中] 沟通项目需求 ← 当前\n- [ ] 筛选商户\n"
        state_tree_v2: str = (
            "- [完成] 沟通项目需求 → 小保养\n"
            "- [进行中] 筛选匹配商户 ← 当前\n"
            "- [ ] 执行预订\n"
        )
        slice_v1: str = "切片v1_project_saving"
        slice_v2: str = "切片v2_merchant_search"
        call_count: int = 0

        async def counting_navigator(
            message: str,
            state_tree: str | None,
            deps: Any,
        ) -> list[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ["project_saving"]
            return ["merchant_search"]

        with (
            patch("src.business_map_hook.state_tree_service") as mock_tree_svc,
            patch("src.business_map_hook.business_map_service") as mock_biz_svc,
            patch.object(
                preprocessor,
                "_call_navigator",
                side_effect=counting_navigator,
            ),
        ):
            # 第一次调用：首次请求（R1），状态树 v1
            mock_tree_svc.read.return_value = state_tree_v1
            mock_biz_svc.assemble_slice.return_value = slice_v1
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="我想做保养",
            )
            assert call_count == 1
            assert preprocessor._nav_state_trees[session_id] == state_tree_v1

            # 第二次调用：状态树变为 v2（R2 命中），即使消息很短也调用
            mock_tree_svc.read.return_value = state_tree_v2
            mock_biz_svc.assemble_slice.return_value = slice_v2
            await preprocessor(
                user_id=user_id,
                session_id=session_id,
                deps=MagicMock(),
                message="嗯",
            )
            assert call_count == 2

        # 切片应被更新为 v2
        assert preprocessor._slices[session_id] == slice_v2
        # 导航快照更新为 v2
        assert preprocessor._nav_state_trees[session_id] == state_tree_v2

"""HlscContextFormatter 场景上下文格式化测试。

覆盖：
- _format_scene_context 输出格式
  - 包含 [当前场景] [目标] [已有信息] [可用工具] [可用 Skill] [策略]
  - target_slots dict 和对象两种形式
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock

# hlsc_context 在 mainagent/src 目录
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_MAINAGENT_SRC: Path = _PROJECT_ROOT / "mainagent" / "src"
if str(_MAINAGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_MAINAGENT_SRC))

from business_map_hook import SceneContext
from hlsc_context import HlscContextFormatter, HlscRequestContext


# ============================================================
# 辅助构造
# ============================================================


def _make_slot_state(slots: dict[str, str | None]) -> MagicMock:
    """构造模拟的 SlotState 对象。"""
    mock: MagicMock = MagicMock()
    mock.slots = slots
    return mock


def _make_scene_context(
    *,
    scene_name: str = "直接表达项目",
    goal: str = "匹配养车项目",
    target_slots: dict[str, Any] | None = None,
    tools: list[str] | None = None,
    allowed_skills: list[str] | None = None,
    strategy: str = "直接匹配项目。",
    slot_state_slots: dict[str, str | None] | None = None,
) -> SceneContext:
    """构造测试用 SceneContext。"""
    if target_slots is None:
        target_slots = {}
    if tools is None:
        tools = []
    if allowed_skills is None:
        allowed_skills = []
    if slot_state_slots is None:
        slot_state_slots = {}

    return SceneContext(
        scene_id="DIRECT_PROJECT",
        scene_name=scene_name,
        goal=goal,
        target_slots=target_slots,
        tools=tools,
        allowed_skills=allowed_skills,
        strategy=strategy,
        slot_state=_make_slot_state(slot_state_slots),
    )


# ============================================================
# 测试类
# ============================================================


class TestFormatSceneContext:
    """_format_scene_context 格式化测试。"""

    def test_contains_scene_name(self) -> None:
        """输出包含 [当前场景]。"""
        ctx: SceneContext = _make_scene_context(scene_name="直接表达项目")
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[当前场景] 直接表达项目" in result

    def test_contains_goal(self) -> None:
        """输出包含 [目标]。"""
        ctx: SceneContext = _make_scene_context(goal="匹配养车项目")
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[目标] 匹配养车项目" in result

    def test_contains_filled_slot(self) -> None:
        """输出 [已有信息] 包含有值的槽位。"""
        ctx: SceneContext = _make_scene_context(
            slot_state_slots={"project_id": "502", "merchant": None},
        )
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[已有信息]" in result
        assert "project_id: 502" in result

    def test_contains_pending_slot_dict_form(self) -> None:
        """target_slots 为 dict 形式时显示待收集信息。"""
        ctx: SceneContext = _make_scene_context(
            slot_state_slots={"project_id": None},
            target_slots={
                "project_id": {
                    "label": "养车项目ID",
                    "method": "调用 match_project",
                }
            },
        )
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "养车项目ID" in result
        assert "待收集" in result
        assert "match_project" in result

    def test_contains_pending_slot_object_form(self) -> None:
        """target_slots 为对象形式时显示待收集信息。"""

        @dataclass
        class FakeTargetSlot:
            label: str = "养车项目ID"
            method: str = "调用 match_project"

        ctx: SceneContext = _make_scene_context(
            slot_state_slots={"project_id": None},
            target_slots={"project_id": FakeTargetSlot()},
        )
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "养车项目ID" in result
        assert "待收集" in result

    def test_contains_tools(self) -> None:
        """输出包含 [可用工具]。"""
        ctx: SceneContext = _make_scene_context(tools=["match_project", "search_shops"])
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[可用工具] match_project, search_shops" in result

    def test_empty_tools(self) -> None:
        """无工具时显示 (无)。"""
        ctx: SceneContext = _make_scene_context(tools=[])
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[可用工具] (无)" in result

    def test_contains_skills(self) -> None:
        """输出包含 [可用 Skill]。"""
        ctx: SceneContext = _make_scene_context(allowed_skills=["diagnose-car", "platform-intro"])
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[可用 Skill] diagnose-car, platform-intro" in result

    def test_empty_skills(self) -> None:
        """无 skill 时显示 (无)。"""
        ctx: SceneContext = _make_scene_context(allowed_skills=[])
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[可用 Skill] (无)" in result

    def test_contains_strategy(self) -> None:
        """输出包含 [策略]。"""
        ctx: SceneContext = _make_scene_context(strategy="直接匹配项目。")
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)
        assert "[策略]" in result
        assert "直接匹配项目。" in result

    def test_full_output_order(self) -> None:
        """输出各节的顺序正确。"""
        ctx: SceneContext = _make_scene_context(
            scene_name="测试场景",
            goal="测试目标",
            tools=["tool_a"],
            allowed_skills=["skill_a"],
            strategy="测试策略",
            slot_state_slots={"a": "1"},
        )
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter._format_scene_context(ctx)

        # 验证顺序
        scene_pos: int = result.index("[当前场景]")
        goal_pos: int = result.index("[目标]")
        info_pos: int = result.index("[已有信息]")
        tools_pos: int = result.index("[可用工具]")
        skills_pos: int = result.index("[可用 Skill]")
        strategy_pos: int = result.index("[策略]")

        assert scene_pos < goal_pos < info_pos < tools_pos < skills_pos < strategy_pos


class TestHlscContextFormatterFormat:
    """HlscContextFormatter.format 集成测试。"""

    def test_format_with_orchestrator(self) -> None:
        """有 orchestrator 时注入场景上下文。"""
        ctx: SceneContext = _make_scene_context(scene_name="测试场景")

        mock_orchestrator: MagicMock = MagicMock()
        mock_orchestrator.current_session_id = "test-session"
        mock_orchestrator.get_scene_context.return_value = ctx

        formatter: HlscContextFormatter = HlscContextFormatter(orchestrator=mock_orchestrator)
        request: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(request)

        assert "[当前场景] 测试场景" in result

    def test_format_without_orchestrator(self) -> None:
        """无 orchestrator 时只输出基础上下文。"""
        formatter: HlscContextFormatter = HlscContextFormatter()
        request: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(request)

        assert "[当前场景]" not in result
        assert "current_car" in result

    def test_format_with_dict_context(self) -> None:
        """dict 类型的 context 能正确转换。"""
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter.format({})  # type: ignore
        assert "current_car" in result

    def test_format_with_invalid_context(self) -> None:
        """非 HlscRequestContext 类型返回空字符串。"""
        formatter: HlscContextFormatter = HlscContextFormatter()
        result: str = formatter.format("not a context")  # type: ignore
        assert result == ""

    def test_format_no_scene_context(self) -> None:
        """orchestrator 存在但无场景上下文时不注入。"""
        mock_orchestrator: MagicMock = MagicMock()
        mock_orchestrator.current_session_id = "test-session"
        mock_orchestrator.get_scene_context.return_value = None

        formatter: HlscContextFormatter = HlscContextFormatter(orchestrator=mock_orchestrator)
        request: HlscRequestContext = HlscRequestContext()
        result: str = formatter.format(request)

        assert "[当前场景]" not in result

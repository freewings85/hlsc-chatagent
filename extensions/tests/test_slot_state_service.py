"""槽位状态服务测试。

覆盖：
- SlotState 模型：has_slot / set_slot / reset_slots / get_filled_slots
- 持久化：write + read 一致性
- get_or_create：首次创建 / 已存在读取
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hlsc.services.scene_service import StageConfig
from hlsc.services.slot_state_service import (
    SceneHistoryEntry,
    SlotState,
    SlotStateService,
)


# ============================================================
# SlotState 模型测试
# ============================================================


class TestSlotState:
    """SlotState 数据模型测试。"""

    def test_has_slot_true(self) -> None:
        """has_slot：有值返回 True。"""
        state: SlotState = SlotState(slots={"project_id": "502"})
        assert state.has_slot("project_id") is True

    def test_has_slot_false_none(self) -> None:
        """has_slot：值为 None 返回 False。"""
        state: SlotState = SlotState(slots={"project_id": None})
        assert state.has_slot("project_id") is False

    def test_has_slot_false_missing(self) -> None:
        """has_slot：不存在的 key 返回 False。"""
        state: SlotState = SlotState(slots={})
        assert state.has_slot("project_id") is False

    def test_set_slot(self) -> None:
        """set_slot：设置槽位值。"""
        state: SlotState = SlotState(slots={"project_id": None})
        state.set_slot("project_id", "502")
        assert state.slots["project_id"] == "502"

    def test_set_slot_new_key(self) -> None:
        """set_slot：设置不存在的 key。"""
        state: SlotState = SlotState(slots={})
        state.set_slot("new_key", "value")
        assert state.slots["new_key"] == "value"

    def test_set_slot_to_none(self) -> None:
        """set_slot：设置为 None。"""
        state: SlotState = SlotState(slots={"project_id": "502"})
        state.set_slot("project_id", None)
        assert state.slots["project_id"] is None

    def test_reset_slots(self) -> None:
        """reset_slots：重置指定槽位为 None。"""
        state: SlotState = SlotState(
            slots={"project_id": "502", "merchant": "店A", "other": "val"}
        )
        state.reset_slots(["project_id", "merchant"])
        assert state.slots["project_id"] is None
        assert state.slots["merchant"] is None
        assert state.slots["other"] == "val"  # 不受影响

    def test_reset_slots_nonexistent_key(self) -> None:
        """reset_slots：不存在的 key 不报错。"""
        state: SlotState = SlotState(slots={"a": "1"})
        state.reset_slots(["nonexistent"])  # 不应抛异常
        assert "nonexistent" not in state.slots

    def test_get_filled_slots(self) -> None:
        """get_filled_slots：只返回有值的槽位。"""
        state: SlotState = SlotState(
            slots={"project_id": "502", "merchant": None, "time": "10:00"}
        )
        filled: dict[str, str] = state.get_filled_slots()
        assert filled == {"project_id": "502", "time": "10:00"}

    def test_get_filled_slots_empty(self) -> None:
        """get_filled_slots：全为 None 返回空 dict。"""
        state: SlotState = SlotState(slots={"a": None, "b": None})
        filled: dict[str, str] = state.get_filled_slots()
        assert filled == {}

    def test_default_values(self) -> None:
        """默认值正确。"""
        state: SlotState = SlotState()
        assert state.slots == {}
        assert state.scene_history == []
        assert state.current_scene is None

    def test_scene_history(self) -> None:
        """场景历史记录。"""
        state: SlotState = SlotState(
            scene_history=[
                SceneHistoryEntry(scene="CASUAL_CHAT", turns=3),
                SceneHistoryEntry(scene="DIRECT_PROJECT", turns=1),
            ]
        )
        assert len(state.scene_history) == 2
        assert state.scene_history[0].scene == "CASUAL_CHAT"
        assert state.scene_history[0].turns == 3


# ============================================================
# 持久化测试
# ============================================================


class TestSlotStatePersistence:
    """SlotStateService 持久化读写测试。"""

    def test_write_and_read(self, tmp_path: Path) -> None:
        """write + read 一致性。"""
        svc: SlotStateService = SlotStateService()
        state: SlotState = SlotState(
            slots={"project_id": "502", "merchant": None},
            current_scene="DIRECT_PROJECT",
        )
        svc.write(tmp_path, state)

        loaded: SlotState | None = svc.read(tmp_path)
        assert loaded is not None
        assert loaded.slots["project_id"] == "502"
        assert loaded.slots["merchant"] is None
        assert loaded.current_scene == "DIRECT_PROJECT"

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        """读取不存在的文件返回 None。"""
        svc: SlotStateService = SlotStateService()
        result: SlotState | None = svc.read(tmp_path)
        assert result is None

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """读取空文件返回 None。"""
        svc: SlotStateService = SlotStateService()
        empty_file: Path = tmp_path / "slot_state.json"
        empty_file.write_text("", encoding="utf-8")
        result: SlotState | None = svc.read(tmp_path)
        assert result is None

    def test_read_invalid_json(self, tmp_path: Path) -> None:
        """读取无效 JSON 返回 None（不抛异常）。"""
        svc: SlotStateService = SlotStateService()
        bad_file: Path = tmp_path / "slot_state.json"
        bad_file.write_text("{invalid json}", encoding="utf-8")
        result: SlotState | None = svc.read(tmp_path)
        assert result is None

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        """write 自动创建不存在的目录。"""
        svc: SlotStateService = SlotStateService()
        nested_dir: Path = tmp_path / "a" / "b" / "c"
        state: SlotState = SlotState(slots={"x": "1"})
        svc.write(nested_dir, state)

        assert (nested_dir / "slot_state.json").exists()

    def test_overwrite(self, tmp_path: Path) -> None:
        """覆盖写入。"""
        svc: SlotStateService = SlotStateService()
        state1: SlotState = SlotState(slots={"a": "1"})
        svc.write(tmp_path, state1)

        state2: SlotState = SlotState(slots={"a": "2", "b": "3"})
        svc.write(tmp_path, state2)

        loaded: SlotState | None = svc.read(tmp_path)
        assert loaded is not None
        assert loaded.slots["a"] == "2"
        assert loaded.slots["b"] == "3"


# ============================================================
# get_or_create 测试
# ============================================================


class TestGetOrCreate:
    """get_or_create 测试。"""

    @staticmethod
    def _make_config() -> "SceneServiceConfig":
        """构造最小 SceneServiceConfig 用于测试。"""
        from hlsc.services.scene_service import (
            BmaConfig,
            FactorConfig,
            SceneServiceConfig,
        )

        return SceneServiceConfig(
            factors=FactorConfig(
                slot_factors=[], keyword_factors=[],
                bma_bool_factors=[], bma_enum_factors=[],
            ),
            bma_config=BmaConfig(
                max_factors_per_call=10, parallel_enabled=True, groups=[],
            ),
            stages={
                "S1": StageConfig(
                    name="S1", description="desc",
                    slots={"project_id": {}, "vehicle_info": {}},
                ),
                "S2": StageConfig(
                    name="S2", description="desc",
                    slots={"merchant": {}, "booking_time": {}},
                ),
            },
            tree=[],
            scenes={},
        )

    def test_create_new(self, tmp_path: Path) -> None:
        """首次创建：从 config stages 收集所有 slot 名。"""
        svc: SlotStateService = SlotStateService()
        config = self._make_config()

        state: SlotState = svc.get_or_create(tmp_path, config)
        assert "project_id" in state.slots
        assert "vehicle_info" in state.slots
        assert "merchant" in state.slots
        assert "booking_time" in state.slots
        # 所有初始值为 None
        for val in state.slots.values():
            assert val is None

    def test_create_persists_to_disk(self, tmp_path: Path) -> None:
        """首次创建后持久化到磁盘。"""
        svc: SlotStateService = SlotStateService()
        config = self._make_config()

        svc.get_or_create(tmp_path, config)

        # 磁盘上有文件
        assert (tmp_path / "slot_state.json").exists()

    def test_get_existing(self, tmp_path: Path) -> None:
        """已存在时直接读取，不重新创建。"""
        svc: SlotStateService = SlotStateService()
        config = self._make_config()

        # 先手动写入
        existing: SlotState = SlotState(
            slots={"project_id": "502"}, current_scene="CUSTOM"
        )
        svc.write(tmp_path, existing)

        # get_or_create 应返回已有状态
        state: SlotState = svc.get_or_create(tmp_path, config)
        assert state.slots["project_id"] == "502"
        assert state.current_scene == "CUSTOM"

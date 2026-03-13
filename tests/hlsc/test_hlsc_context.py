"""HlscRequestContext 和 hlsc_context_formatter 测试"""

from __future__ import annotations

import pytest

from src.sdk._agent.memory.inmemory_context_service import InMemoryContextService
from src.hlsc.mainagent.hlsc_context import HlscRequestContext, hlsc_context_formatter
from src.hlsc.mainagent.hlsc_core import CarInfo, LocationInfo


class TestHlscRequestContext:

    def test_empty(self) -> None:
        ctx = HlscRequestContext()
        assert ctx.current_car is None
        assert ctx.current_location is None

    def test_with_car_and_location(self) -> None:
        ctx = HlscRequestContext(
            current_car=CarInfo(car_model_id="123", car_model_name="宝马3系"),
            current_location=LocationInfo(address="浦东新区张江"),
        )
        assert ctx.current_car.car_model_name == "宝马3系"
        assert ctx.current_location.address == "浦东新区张江"


class TestHlscContextFormatter:

    def test_car_change(self) -> None:
        result = hlsc_context_formatter({
            "current_car": {"car_model_id": "123", "car_model_name": "宝马3系"},
        })
        assert "宝马3系" in result
        assert "用户车辆" in result

    def test_location_change(self) -> None:
        result = hlsc_context_formatter({
            "current_location": {"address": "浦东新区张江"},
        })
        assert "浦东新区张江" in result
        assert "用户位置" in result

    def test_both_change(self) -> None:
        result = hlsc_context_formatter({
            "current_car": {"car_model_id": "123", "car_model_name": "奔驰C级"},
            "current_location": {"address": "徐汇区漕河泾"},
        })
        assert "奔驰C级" in result
        assert "漕河泾" in result

    def test_fallback_unknown_keys(self) -> None:
        result = hlsc_context_formatter({"some_new_field": "value"})
        assert "some_new_field" in result


class TestHlscContextDiff:

    async def test_diff_with_hlsc_context(self) -> None:
        service = InMemoryContextService(formatter=hlsc_context_formatter)
        ctx1 = HlscRequestContext(
            current_car=CarInfo(car_model_id="1", car_model_name="宝马3系"),
            current_location=LocationInfo(address="张江"),
        )
        await service.set("u1", "s1", ctx1)

        # 只改了位置
        ctx2 = HlscRequestContext(
            current_car=CarInfo(car_model_id="1", car_model_name="宝马3系"),
            current_location=LocationInfo(address="漕河泾"),
        )
        changed = await service.diff("u1", "s1", ctx2)
        assert changed is not None
        assert "current_location" in changed
        assert "current_car" not in changed

        # format
        text = service.format_changed(changed)
        assert "漕河泾" in text

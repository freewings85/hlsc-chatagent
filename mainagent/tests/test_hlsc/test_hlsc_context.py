"""HlscRequestContext 和 HlscContextFormatter 测试"""

from __future__ import annotations

from hlsc.models import CarInfo, LocationInfo
from src.hlsc_context import HlscContextFormatter, HlscRequestContext


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

    def test_with_car_and_location(self) -> None:
        formatter = HlscContextFormatter()
        ctx = HlscRequestContext(
            current_car=CarInfo(car_model_id="123", car_model_name="宝马3系"),
            current_location=LocationInfo(address="浦东新区张江", lat=31.2, lng=121.5),
        )
        result = formatter.format(ctx)
        assert "### request_context" in result
        assert "current_car(car_model_id=123, car_model_name=宝马3系" in result
        assert "current_location(address=浦东新区张江" in result

    def test_empty_context(self) -> None:
        formatter = HlscContextFormatter()
        ctx = HlscRequestContext()
        result = formatter.format(ctx)
        assert "current_car: (未设置)" in result
        assert "current_location: (未设置)" in result

    def test_car_only(self) -> None:
        formatter = HlscContextFormatter()
        ctx = HlscRequestContext(
            current_car=CarInfo(car_model_id="456", car_model_name="奔驰C级"),
        )
        result = formatter.format(ctx)
        assert "car_model_name=奔驰C级" in result
        assert "current_location: (未设置)" in result

    def test_location_only(self) -> None:
        formatter = HlscContextFormatter()
        ctx = HlscRequestContext(
            current_location=LocationInfo(address="徐汇区漕河泾", lat=31.17, lng=121.4),
        )
        result = formatter.format(ctx)
        assert "current_car: (未设置)" in result
        assert "address=徐汇区漕河泾" in result

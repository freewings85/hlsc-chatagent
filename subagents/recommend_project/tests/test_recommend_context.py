"""RecommendContextFormatter 单元测试"""

from __future__ import annotations

import pytest

from src.recommend_context import (
    RecommendContextFormatter,
    RecommendRequestContext,
    VehicleInfo,
)


class TestRecommendContextFormatter:
    def setup_method(self) -> None:
        self.formatter = RecommendContextFormatter()

    def test_format_full_vehicle_info(self) -> None:
        """完整车辆信息应全部展示。"""
        ctx = RecommendRequestContext(
            vehicle_info=VehicleInfo(
                car_model_name="2024款 宝马 325Li",
                car_key="bmw-325li-2024",
                vin_code="WBAJB1105MCJ12345",
                mileage_km=35000.0,
                car_age_year=2.5,
            ),
        )
        result = self.formatter.format(ctx)
        assert "[request_context]" in result
        assert "宝马 325Li" in result
        assert "bmw-325li-2024" in result
        assert "WBAJB1105MCJ12345" in result
        assert "35000" in result
        assert "2.5" in result

    def test_format_partial_vehicle_info(self) -> None:
        """只有部分字段时只展示非空字段。"""
        ctx = RecommendRequestContext(
            vehicle_info=VehicleInfo(
                car_model_name="大众 Polo",
                mileage_km=20000.0,
            ),
        )
        result = self.formatter.format(ctx)
        assert "大众 Polo" in result
        assert "20000" in result
        assert "vin_code" not in result
        assert "car_key" not in result

    def test_format_no_vehicle_info(self) -> None:
        """无车辆信息时显示未设置。"""
        ctx = RecommendRequestContext(vehicle_info=None)
        result = self.formatter.format(ctx)
        assert "未设置" in result

    def test_format_dict_input(self) -> None:
        """从 dict（A2A metadata）构造时也应正常工作。"""
        ctx_dict = {
            "vehicle_info": {
                "car_model_name": "奥迪 A4L",
                "car_age_year": 3.0,
            },
        }
        result = self.formatter.format(ctx_dict)
        assert "奥迪 A4L" in result
        assert "3.0" in result

    def test_format_empty_dict(self) -> None:
        """空 dict 应返回空字符串。"""
        result = self.formatter.format({})
        assert "未设置" in result

    def test_format_invalid_dict(self) -> None:
        """无法解析的 dict 应返回空字符串。"""
        result = self.formatter.format({"invalid_field": 123})
        # RecommendRequestContext 会忽略未知字段，vehicle_info 为 None
        assert "未设置" in result

    def test_format_wrong_type(self) -> None:
        """传入非 dict 非 RecommendRequestContext 应返回空字符串。"""
        result = self.formatter.format("not a context")
        assert result == ""

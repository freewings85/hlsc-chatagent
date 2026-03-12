"""话痨说车业务请求上下文。"""

from __future__ import annotations

from typing import Any

from src.common.request_context import RequestContext
from src.hlsc.hlsc_core import CarInfo, LocationInfo


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None


def hlsc_context_formatter(changed: dict[str, Any]) -> str:
    """将变化的上下文字段格式化为自然语言提示。"""
    parts: list[str] = []

    if "current_car" in changed and changed["current_car"] is not None:
        car = changed["current_car"]
        name = car.get("car_model_name", "") if isinstance(car, dict) else car.car_model_name
        if name:
            parts.append(f"用户车辆: {name}")

    if "current_location" in changed and changed["current_location"] is not None:
        loc = changed["current_location"]
        addr = loc.get("address", "") if isinstance(loc, dict) else loc.address
        if addr:
            parts.append(f"用户位置: {addr}")

    if not parts:
        # fallback: 列出所有变化的 key
        parts.append("用户上下文已更新: " + ", ".join(changed.keys()))

    return "当前用户信息：\n" + "\n".join(parts)

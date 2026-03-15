"""话痨说车业务请求上下文。"""

from __future__ import annotations

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行，确保 LLM 始终能看到当前车辆和位置。
    """

    def format(self, context: RequestContext) -> str:
        if not isinstance(context, HlscRequestContext):
            return ""

        parts: list[str] = []

        if context.current_car is not None:
            car = context.current_car
            parts.append(f"car_model_id: {car.car_model_id} ({car.car_model_name})")
        else:
            parts.append("car_model_id: (未设置)")

        if context.current_location is not None:
            loc = context.current_location
            lat = loc.lat or "未知"
            lng = loc.lng or "未知"
            parts.append(f"location: {loc.address} (lat={lat}, lng={lng})")
        else:
            parts.append("location: (未设置)")

        return "[request_context]\n" + "\n".join(parts)

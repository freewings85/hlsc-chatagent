"""话痨说车业务请求上下文。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo


class SceneInfo(BaseModel):
    """场景判定信息（由外部小模型产出并写入 request_context）。"""

    scene_type: Literal["chat", "clarify", "execute"] = Field(
        default="clarify",
        description="当前场景类型",
    )
    confidence: float = Field(
        default=0.0,
        description="场景判定置信度（0~1）",
    )
    request_id: str = Field(
        default="",
        description="该场景判定对应的 request_id",
    )


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None
    scene_info: SceneInfo | None = None


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行，确保 LLM 始终能看到当前车辆和位置。
    """

    def format(self, context: RequestContext) -> str:
        # 支持 dict（从 HTTP 请求直接传入）和 HlscRequestContext
        if isinstance(context, dict):
            try:
                context = HlscRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, HlscRequestContext):
            return ""

        parts: list[str] = []

        if context.current_car is not None:
            car = context.current_car
            parts.append(
                f"current_car(car_model_id={car.car_model_id}, "
                f"car_model_name={car.car_model_name}, "
                f"vin_code={car.vin_code})"
            )
        else:
            parts.append("current_car: (未设置)")

        if context.current_location is not None:
            loc = context.current_location
            parts.append(
                f"current_location(address={loc.address}, "
                f"lat={loc.lat}, lng={loc.lng})"
            )
        else:
            parts.append("current_location: (未设置)")

        return "[request_context]: " + ", ".join(parts)

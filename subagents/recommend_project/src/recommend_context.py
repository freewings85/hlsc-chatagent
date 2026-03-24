"""RecommendProject 请求上下文。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from agent_sdk._common.request_context import ContextFormatter, RequestContext


class VehicleInfo(BaseModel):
    """车辆信息（由 MainAgent 通过 A2A context 传入）"""

    car_model_name: str = Field(default="", description="车型名称，如 2024款 宝马 325Li")
    car_model_id: str = Field(default="", description="车型编码，用于精确匹配项目")
    vin_code: Optional[str] = Field(default=None, description="VIN 码（17 位），如 LSVFA49J952001313")
    mileage_km: Optional[float] = Field(default=None, description="当前里程数（千米），如 35000.0")
    car_age_year: Optional[float] = Field(default=None, description="车龄（年），如 2.5")


class RecommendRequestContext(RequestContext):
    """推荐项目请求上下文。"""

    vehicle_info: VehicleInfo | None = None


class RecommendContextFormatter(ContextFormatter):
    """将 RecommendRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行，确保 LLM 始终能看到当前车辆信息。
    """

    def format(self, context: RequestContext) -> str:
        # 支持 dict（从 A2A metadata 传入）和 RecommendRequestContext
        if isinstance(context, dict):
            try:
                context = RecommendRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, RecommendRequestContext):
            return ""

        if context.vehicle_info is None:
            return "[request_context]: vehicle_info: (未设置)"

        v = context.vehicle_info
        parts: list[str] = []
        if v.car_model_name:
            parts.append(f"car_model_name={v.car_model_name}")
        if v.car_model_id:
            parts.append(f"car_model_id={v.car_model_id}")
        if v.vin_code:
            parts.append(f"vin_code={v.vin_code}")
        if v.mileage_km is not None:
            parts.append(f"mileage_km={v.mileage_km}")
        if v.car_age_year is not None:
            parts.append(f"car_age_year={v.car_age_year}")

        if not parts:
            return "[request_context]: vehicle_info: (未设置)"

        return "[request_context]: vehicle_info(" + ", ".join(parts) + ")"

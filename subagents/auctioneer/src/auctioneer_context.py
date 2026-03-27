"""Auctioneer 请求上下文。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_sdk._common.request_context import ContextFormatter, RequestContext


class AuctioneerRequestContext(RequestContext):
    """拍卖师请求上下文（由 MainAgent 通过 A2A context 传入）"""

    project_ids: list[str] = Field(default_factory=list, description="项目 ID 列表")
    shop_ids: list[str] = Field(default_factory=list, description="商户 ID 列表")
    car_model_id: str = Field(default="", description="车型 ID")
    price: str = Field(default="", description="车主出的一口价")
    booking_time: str = Field(default="", description="到店时间")


class AuctioneerContextFormatter(ContextFormatter):
    """将 AuctioneerRequestContext 格式化为注入 LLM 的文本。"""

    def format(self, context: RequestContext) -> str:
        if isinstance(context, dict):
            try:
                context = AuctioneerRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, AuctioneerRequestContext):
            return ""

        parts: list[str] = []
        if context.project_ids:
            parts.append(f"project_ids={context.project_ids}")
        if context.shop_ids:
            parts.append(f"shop_ids={context.shop_ids}")
        if context.car_model_id:
            parts.append(f"car_model_id={context.car_model_id}")
        if context.price:
            parts.append(f"price={context.price}")
        if context.booking_time:
            parts.append(f"booking_time={context.booking_time}")

        if not parts:
            return "[request_context]: auction_params: (未设置)"

        return "[request_context]: auction_params(" + ", ".join(parts) + ")"

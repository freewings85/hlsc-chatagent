"""拍卖师数据模型。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AuctionStatus(str, Enum):
    """拍卖任务状态。"""
    PENDING = "pending"
    POLLING = "polling"
    COMPLETED = "completed"
    FAILED = "failed"


class AuctionParams(BaseModel):
    """拍卖任务参数。"""
    session_id: str = Field(description="会话 ID")
    project_ids: list[str] = Field(description="项目 ID 列表")
    shop_ids: list[str] = Field(description="参与竞标的商户 ID 列表")
    car_model_id: str = Field(default="", description="车型 ID")
    price: str = Field(default="", description="车主期望价格（commission 模式）")
    plan_mode: Literal["commission", "bidding"] = Field(description="预订模式")
    booking_time: str = Field(default="", description="到店时间")


class Quote(BaseModel):
    """商户报价。"""
    shop_id: str
    shop_name: str
    quote_price: float
    responded_at: float = Field(default=0.0, description="响应时间戳")


class AuctionResult(BaseModel):
    """拍卖任务结果。"""
    task_id: str
    status: AuctionStatus
    total_merchants: int
    total_responded: int
    quotes: list[Quote] = Field(default_factory=list)
    best_offer: Quote | None = None
    recommendation: str = ""

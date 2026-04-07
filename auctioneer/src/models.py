"""拍卖师数据模型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AuctionStatus(str, Enum):
    """拍卖任务状态。"""
    PENDING = "pending"
    POLLING = "polling"
    COMPLETED = "completed"
    FAILED = "failed"


class OrderStatus:
    """服务订单状态常量（对应 /serviceorder/detail 的 orderStatus）。"""
    CANCELLED: int = -10
    INQUIRING: int = 0
    MERCHANT_QUOTED: int = 10
    OWNER_ORDERED: int = 20
    ARRIVED: int = 30
    COMPLETED: int = 40
    VERIFIED: int = 50


class AuctionParams(BaseModel):
    """拍卖任务参数（前端只需传 order_id）。"""
    order_id: str = Field(description="服务订单 ID")
    session_id: str = Field(default="", description="会话 ID")


class Offer(BaseModel):
    """商户报价（对齐 /serviceorder/detail 的 offers 结构）。"""
    offer_id: str = Field(description="报价 ID")
    commercial_id: int = Field(description="商户 ID（用于 commit 接口）")
    commercial_name: str = Field(description="商户名称")
    offer_status: int = Field(default=0, description="报价状态：0=未报价, 10=已报价")
    offer_price: float = Field(default=0.0, description="报价金额")
    offer_remark: str = Field(default="", description="报价备注")
    offer_voice: list[str] = Field(default_factory=list, description="商户报价详情（返现、赠品等自然语言描述）")
    offer_time: str | None = Field(default=None, description="报价时间")


class PollResult(BaseModel):
    """单次轮询结果（activity 返回给 workflow）。"""
    order_status: int = Field(description="订单状态码")
    order_status_desc: str = Field(default="", description="订单状态描述")
    offers: list[Offer] = Field(default_factory=list, description="所有报价（含未报价的）")


class AuctionDecision(BaseModel):
    """LLM 决策结果（structured output）。"""
    commercial_id: int = Field(description="选中的商户 ID")
    commercial_name: str = Field(description="选中的商户名称")
    reason: str = Field(description="选择理由")


class AuctionResult(BaseModel):
    """拍卖任务结果。"""
    task_id: str = Field(description="Temporal workflow ID")
    order_id: str = Field(description="服务订单 ID")
    order_status: int = Field(default=0, description="订单状态码")
    order_status_desc: str = Field(default="", description="订单状态描述")
    status: AuctionStatus = Field(description="拍卖任务状态")
    total_merchants: int = Field(default=0, description="参与商户总数")
    total_responded: int = Field(default=0, description="已报价商户数")
    offers: list[Offer] = Field(default_factory=list, description="已报价列表（按价格排序）")
    best_offer: Offer | None = Field(default=None, description="最优报价")
    recommendation: str = Field(default="", description="LLM 推荐文本")

"""拍卖 Activities：轮询报价 + 广播报价 + LLM 选择 + 提交订单 + 取消订单。"""

from __future__ import annotations

import json

from temporalio import activity

from src.services.serviceorder_service import serviceorder_service
from src.models import AuctionDecision, PollResult, Offer


@activity.defn(name="poll_offers")
async def poll_offers_activity(order_id: str) -> PollResult:
    """调用 /serviceorder/detail 获取订单状态和商户报价。"""
    activity.logger.info("  [poll] 查询订单 %s", order_id)

    data: dict = await serviceorder_service.get_order_detail(order_id)

    order_status: int = data.get("orderStatus", 0)
    order_status_desc: str = data.get("orderStatusDesc", "")
    raw_offers: list[dict] = data.get("offers", [])

    offers: list[Offer] = [
        Offer(
            offer_id=offer.get("offerId", ""),
            commercial_id=offer.get("commercialId", 0),
            commercial_name=offer.get("commercialName", ""),
            offer_status=offer.get("offerStatus", 0),
            offer_price=float(offer.get("offerPrice", 0.0)),
            offer_remark=offer.get("offerRemark", ""),
            offer_voice=offer.get("offerVoice", []),
            offer_time=offer.get("offerTime"),
        )
        for offer in raw_offers
    ]

    responded: list[Offer] = [q for q in offers if q.offer_status > 0]
    pending: list[Offer] = [q for q in offers if q.offer_status == 0]

    activity.logger.info(
        "  [poll] orderStatus=%d(%s) | 已报价=%d | 未报价=%d",
        order_status, order_status_desc, len(responded), len(pending),
    )
    for q in responded:
        activity.logger.info(
            "  ✓ %s (ID:%d) ¥%.2f", q.commercial_name, q.commercial_id, q.offer_price,
        )

    return PollResult(
        order_status=order_status,
        order_status_desc=order_status_desc,
        offers=offers,
    )


@activity.defn(name="broadcast_offers")
async def broadcast_offers_activity(args: list) -> None:
    """广播报价信息给所有商户。支持自定义催单消息。

    args: [order_id, offers, reminder?]
      - reminder 可选，有则追加到广播末尾（如"还剩 1 分钟"催单）
    """
    order_id: str = args[0]
    offers: list[Offer] = [Offer(**q) if isinstance(q, dict) else q for q in args[1]]
    reminder: str = args[2] if len(args) > 2 else ""

    responded: list[Offer] = [q for q in offers if q.offer_status > 0]

    lines: list[str] = []
    if responded:
        lines.append(f"当前已有 {len(responded)} 家商户报价：")
        for q in sorted(responded, key=lambda q: q.offer_price):
            lines.append(f"  • {q.commercial_name}：¥{q.offer_price:.2f}")
    if reminder:
        lines.append(reminder)

    content: str = "\n".join(lines) if lines else "暂无报价信息，请各商户尽快报价。"

    activity.logger.info("  [broadcast] order_id=%s\n%s", order_id, content)

    await serviceorder_service.discuss_command(
        order_id=order_id,
        command="broadcast_only",
        content=content,
    )

    activity.logger.info("  [broadcast] 广播完成")


@activity.defn(name="select_best_offer")
async def select_best_offer_activity(offers: list[Offer]) -> AuctionDecision:
    """调 LLM 分析 offer_voice，按决策原则选出最优商户。"""
    from pathlib import Path

    from pydantic_ai import Agent
    from agent_sdk._agent.model import create_model

    activity.logger.info("[select] LLM 分析 %d 条报价", len(offers))

    system_path: Path = Path(__file__).resolve().parent.parent.parent / "prompts" / "templates" / "select_best_offer.md"
    system_prompt: str = system_path.read_text(encoding="utf-8").strip()

    offers_data: list[dict] = [o.model_dump() for o in offers]
    user_message: str = (
        f"以下是 {len(offers)} 家商户的报价数据，请根据决策原则选出最优商户。\n\n"
        f"{json.dumps(offers_data, ensure_ascii=False, indent=2)}"
    )

    agent: Agent[None, AuctionDecision] = Agent(
        create_model(),
        system_prompt=system_prompt,
        output_type=AuctionDecision,
    )
    result = await agent.run(user_message)
    decision: AuctionDecision = result.output

    activity.logger.info(
        "[select] 选中 %s (ID:%d) — %s",
        decision.commercial_name, decision.commercial_id, decision.reason,
    )
    return decision


@activity.defn(name="commit_order")
async def commit_order_activity(args: list) -> None:
    """提交订单：确认选中商户。args: [order_id, commercial_id]"""
    order_id: str = args[0]
    commercial_id: int = args[1]
    activity.logger.info("  [commit] order_id=%s, commercial_id=%d", order_id, commercial_id)
    result: dict = await serviceorder_service.commit_order(
        order_id=order_id,
        commercial_id=commercial_id,
        operator_name="AI",
    )
    activity.logger.info("  [commit] 订单已提交, result=%s", result)


@activity.defn(name="cancel_order")
async def cancel_order_activity(order_id: str) -> None:
    """竞价到期无人报价时取消订单。"""
    activity.logger.info("  [cancel] 取消订单 %s", order_id)
    await serviceorder_service.cancel_order(order_id)
    activity.logger.info("  [cancel] 订单已取消")



"""拍卖 Activities：轮询报价 + 广播报价 + LLM 汇总。"""

from __future__ import annotations

from temporalio import activity

from src.services.serviceorder_service import serviceorder_service
from src.models import PollResult, Quote


@activity.defn(name="poll_quotes")
async def poll_quotes_activity(order_id: str) -> PollResult:
    """调用 /serviceorder/detail 获取订单状态和商户报价。"""
    activity.logger.info("  [poll] 查询订单 %s", order_id)

    data: dict = await serviceorder_service.get_order_detail(order_id)

    order_status: int = data.get("orderStatus", 0)
    order_status_desc: str = data.get("orderStatusDesc", "")
    offers: list[dict] = data.get("offers", [])

    quotes: list[Quote] = [
        Quote(
            offer_id=offer.get("offerId", ""),
            commercial_id=offer.get("commercialId", 0),
            commercial_name=offer.get("commercialName", ""),
            offer_status=offer.get("offerStatus", 0),
            offer_price=float(offer.get("offerPrice", 0.0)),
            offer_remark=offer.get("offerRemark", ""),
            offer_time=offer.get("offerTime"),
        )
        for offer in offers
    ]

    responded: list[Quote] = [q for q in quotes if q.offer_status > 0]
    pending: list[Quote] = [q for q in quotes if q.offer_status == 0]

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
        quotes=quotes,
    )


@activity.defn(name="broadcast_quotes")
async def broadcast_quotes_activity(args: list) -> None:
    """广播当前报价信息给所有商户。"""
    order_id: str = args[0]
    quotes: list[Quote] = [Quote(**q) if isinstance(q, dict) else q for q in args[1]]

    responded: list[Quote] = [q for q in quotes if q.offer_status > 0]
    pending: list[Quote] = [q for q in quotes if q.offer_status == 0]

    # 组装广播内容
    lines: list[str] = []
    if responded:
        lines.append(f"当前已有 {len(responded)} 家商户报价：")
        for q in sorted(responded, key=lambda q: q.offer_price):
            lines.append(f"  • {q.commercial_name}：¥{q.offer_price:.2f}")
    if pending:
        lines.append(f"还有 {len(pending)} 家商户尚未报价，请尽快提交。")

    content: str = "\n".join(lines) if lines else "暂无报价信息，请各商户尽快报价。"

    activity.logger.info("  [broadcast] order_id=%s\n%s", order_id, content)

    await serviceorder_service.discuss_command(
        order_id=order_id,
        command="broadcast_only",
        content=content,
    )

    activity.logger.info("  [broadcast] 广播完成")


@activity.defn(name="summarize_quotes")
async def summarize_quotes_activity(quotes: list[Quote]) -> str:
    """按价格排序已报价商户，生成推荐文字。"""
    responded: list[Quote] = [q for q in quotes if q.offer_status > 0]
    activity.logger.info("[summarize] 开始汇总，共 %d 条有效报价", len(responded))

    if not responded:
        activity.logger.info("[summarize] 无报价数据")
        return "未收到任何商户报价，建议重新发起竞标或提高价格。"

    sorted_quotes: list[Quote] = sorted(responded, key=lambda q: q.offer_price)
    best: Quote = sorted_quotes[0]

    for i, q in enumerate(sorted_quotes, start=1):
        tag: str = " ← 推荐" if q.commercial_id == best.commercial_id else ""
        activity.logger.info(
            "  [summarize] #%d %s ¥%.2f%s", i, q.commercial_name, q.offer_price, tag,
        )

    lines: list[str] = [f"共收到 {len(responded)} 家商户报价："]
    for q in sorted_quotes:
        tag = "  ← 推荐" if q.commercial_id == best.commercial_id else ""
        lines.append(f"  • {q.commercial_name}：¥{q.offer_price:.2f}{tag}")
    lines.append(
        f"\n推荐选择【{best.commercial_name}】（商户ID: {best.commercial_id}），"
        f"报价 ¥{best.offer_price:.2f}，为最低报价。"
    )

    return "\n".join(lines)

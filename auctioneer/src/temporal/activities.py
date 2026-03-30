"""拍卖 Activities：轮询报价 + 汇总推荐（mock）。"""

from __future__ import annotations

import random
import time

from temporalio import activity

from src.models import Quote

# 3 家 mock 商户
_MOCK_MERCHANTS: list[dict[str, str]] = [
    {"shop_id": "S001", "shop_name": "朱德保修理厂"},
    {"shop_id": "S002", "shop_name": "张记汽修连锁"},
    {"shop_id": "S003", "shop_name": "老王精洗工作室"},
]


@activity.defn(name="poll_quotes")
async def poll_quotes_activity(responded_shop_ids: list[str]) -> list[Quote]:
    """轮询一次：从未回复商户中随机返回 0-1 个报价（50-100 元）。"""
    responded: set[str] = set(responded_shop_ids)
    pending: list[dict[str, str]] = [
        m for m in _MOCK_MERCHANTS if m["shop_id"] not in responded
    ]

    if not pending:
        activity.logger.info("  [poll] 所有商户已回复，无需轮询")
        return []

    pending_names: str = "、".join(m["shop_name"] for m in pending)
    activity.logger.info("  [poll] 待回复商户：%s", pending_names)

    # 每次轮询有 60% 概率产生一个新报价
    if random.random() > 0.6:
        activity.logger.info("  [poll] 本轮商户未响应")
        return []

    chosen: dict[str, str] = random.choice(pending)
    quote: Quote = Quote(
        shop_id=chosen["shop_id"],
        shop_name=chosen["shop_name"],
        quote_price=round(random.uniform(50.0, 100.0), 1),
        responded_at=time.time(),
    )
    activity.logger.info(
        "  [poll] %s 报价 ¥%.1f", quote.shop_name, quote.quote_price,
    )
    return [quote]


@activity.defn(name="summarize_quotes")
async def summarize_quotes_activity(quotes: list[Quote]) -> str:
    """按价格排序，挑选最低报价并生成推荐文字。"""
    activity.logger.info("[summarize] 开始汇总，共 %d 条报价", len(quotes))

    if not quotes:
        activity.logger.info("[summarize] 无报价数据")
        return "未收到任何商户报价，建议重新发起竞标。"

    sorted_quotes: list[Quote] = sorted(quotes, key=lambda q: q.quote_price)
    best: Quote = sorted_quotes[0]

    for i, q in enumerate(sorted_quotes, start=1):
        tag: str = " ← 推荐" if q.shop_id == best.shop_id else ""
        activity.logger.info(
            "  [summarize] #%d %s ¥%.1f%s", i, q.shop_name, q.quote_price, tag,
        )

    lines: list[str] = [f"共收到 {len(quotes)} 家商户报价："]
    for q in sorted_quotes:
        tag = "  ← 推荐" if q.shop_id == best.shop_id else ""
        lines.append(f"  • {q.shop_name}：¥{q.quote_price}{tag}")
    lines.append(f"\n推荐选择【{best.shop_name}】，报价 ¥{best.quote_price}，为最低报价。")

    return "\n".join(lines)

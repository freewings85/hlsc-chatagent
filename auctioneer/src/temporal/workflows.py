"""拍卖 Workflow：每 10s 轮询 → 催单 → 全部报价提前结束 → LLM 选择 → 自动 commit。

时间线：
  每 10s    — 轮询报价状态，全部报价则提前进入决策
  催单时间  — 广播："已有 N 家报价，还剩 X 分钟"
  到期      — 最终轮询
  决策      — LLM 分析 offer_voice → 选出最优商户 → 自动 commit order
  无人报价  — 自动取消订单
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.models import (
        AuctionDecision,
        AuctionParams,
        AuctionResult,
        AuctionStatus,
        PollResult,
        Offer,
    )
    from src.temporal.activities import (
        broadcast_offers_activity,
        cancel_order_activity,
        commit_order_activity,
        poll_offers_activity,
        select_best_offer_activity,
    )

import os

# 竞价总时长（分钟）
AUCTION_DURATION_MIN: int = int(os.getenv("AUCTION_DURATION_MINUTES", "5"))
AUCTION_DURATION: int = AUCTION_DURATION_MIN * 60
# 催单广播：截止前 N 分钟
REMINDER_BEFORE_MIN: int = int(os.getenv("AUCTION_REMINDER_BEFORE_MINUTES", "1"))
REMINDER_AT: int = AUCTION_DURATION - REMINDER_BEFORE_MIN * 60
# 轮询间隔（秒）
POLL_INTERVAL: int = 10


@workflow.defn
class AuctionWorkflow:
    """拍卖工作流：轮询 → 催单 → LLM 选择 → 自动 commit。"""

    def __init__(self) -> None:
        self._offers: list[Offer] = []
        self._status: AuctionStatus = AuctionStatus.POLLING
        self._order_id: str = ""
        self._order_status: int = 0
        self._order_status_desc: str = ""
        self._recommendation: str = ""
        self._total_merchants: int = 0
        self._reminder_sent: bool = False
        self._elapsed: int = 0

    @workflow.run
    async def run(self, params: AuctionParams) -> AuctionResult:
        task_id: str = workflow.info().workflow_id
        self._order_id = params.order_id

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖启动] task_id=%s | order_id=%s\n"
            "  竞价 %ds，%ds 时催单，每 %ds 轮询\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id, AUCTION_DURATION, REMINDER_AT, POLL_INTERVAL,
        )

        # ── 轮询循环 ──
        all_responded: bool = False
        while self._elapsed < AUCTION_DURATION:
            await workflow.sleep(timedelta(seconds=POLL_INTERVAL))
            self._elapsed += POLL_INTERVAL

            poll_result: PollResult = await workflow.execute_activity(
                poll_offers_activity,
                params.order_id,
                start_to_close_timeout=timedelta(seconds=15),
            )
            self._update_offers(poll_result)

            if self._total_merchants == 0:
                self._total_merchants = len(poll_result.offers)

            responded: list[Offer] = [o for o in self._offers if o.offer_status > 0]
            workflow.logger.info(
                "[%ds] 已报价 %d/%d",
                self._elapsed, len(responded), self._total_merchants,
            )

            # 催单广播（到达催单时间点且未发送过）
            if self._elapsed >= REMINDER_AT and not self._reminder_sent:
                self._reminder_sent = True
                pending_count: int = self._total_merchants - len(responded)
                reminder: str = (
                    f"已有 {len(responded)} 家商户报价，还剩 {REMINDER_BEFORE_MIN} 分钟，请各商户尽快报价。"
                    if pending_count > 0
                    else f"所有 {len(responded)} 家商户已报价，即将截止。"
                )
                workflow.logger.info("[催单] %s", reminder)
                await workflow.execute_activity(
                    broadcast_offers_activity,
                    [params.order_id, self._offers, reminder],
                    start_to_close_timeout=timedelta(seconds=15),
                )

            # 全部报价 → 提前结束轮询
            if self._total_merchants > 0 and len(responded) >= self._total_merchants:
                workflow.logger.info("[提前结束] 所有 %d 家商户已报价", self._total_merchants)
                all_responded = True
                break

        # ── 决策 ──
        responded = [o for o in self._offers if o.offer_status > 0]

        if not responded:
            workflow.logger.info("[取消] 无商户报价，取消订单 %s", params.order_id)
            await workflow.execute_activity(
                cancel_order_activity,
                params.order_id,
                start_to_close_timeout=timedelta(seconds=15),
            )
            self._status = AuctionStatus.FAILED
            return AuctionResult(
                task_id=task_id,
                order_id=params.order_id,
                order_status=self._order_status,
                order_status_desc=self._order_status_desc,
                status=AuctionStatus.FAILED,
                total_merchants=self._total_merchants,
                total_responded=0,
                offers=[],
                best_offer=None,
                recommendation="竞价到期无商户报价，订单已自动取消。",
            )

        # LLM 分析选择最优商户
        decision: AuctionDecision = await workflow.execute_activity(
            select_best_offer_activity,
            responded,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # 自动提交订单
        await workflow.execute_activity(
            commit_order_activity,
            [params.order_id, decision.commercial_id],
            start_to_close_timeout=timedelta(seconds=15),
        )

        best: Offer | None = next(
            (o for o in responded if o.commercial_id == decision.commercial_id),
            None,
        )

        self._status = AuctionStatus.COMPLETED
        self._recommendation = decision.reason
        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖完成] task_id=%s | order_id=%s\n"
            "  已报价 %d/%d 家 | 选中 %s | %s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id,
            len(responded), self._total_merchants,
            decision.commercial_name, decision.reason,
        )

        return AuctionResult(
            task_id=task_id,
            order_id=params.order_id,
            order_status=self._order_status,
            order_status_desc=self._order_status_desc,
            status=AuctionStatus.COMPLETED,
            total_merchants=self._total_merchants,
            total_responded=len(responded),
            offers=responded,
            best_offer=best,
            recommendation=decision.reason,
        )

    def _update_offers(self, poll_result: PollResult) -> None:
        """更新报价和订单状态。"""
        self._offers = poll_result.offers
        self._order_status = poll_result.order_status
        self._order_status_desc = poll_result.order_status_desc

    @workflow.query
    def get_status(self) -> dict[str, object]:
        """实时查询任务进度。"""
        responded: list[Offer] = [o for o in self._offers if o.offer_status > 0]
        return {
            "status": self._status.value,
            "order_id": self._order_id,
            "order_status": self._order_status,
            "order_status_desc": self._order_status_desc,
            "total_merchants": self._total_merchants,
            "total_responded": len(responded),
            "elapsed_seconds": self._elapsed,
            "offers": [o.model_dump() for o in responded],
            "recommendation": self._recommendation,
        }

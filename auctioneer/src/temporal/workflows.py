"""拍卖 Workflow：3 轮固定轮询（10s/20s/30s），前两轮广播，第三轮 LLM 汇总。"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.models import (
        AuctionParams,
        AuctionResult,
        AuctionStatus,
        PollResult,
        Quote,
    )
    from src.temporal.activities import (
        broadcast_quotes_activity,
        poll_quotes_activity,
        summarize_quotes_activity,
    )

# 3 轮轮询间隔（秒）
POLL_INTERVALS: list[int] = [10, 10, 10]
TOTAL_ROUNDS: int = len(POLL_INTERVALS)


@workflow.defn
class AuctionWorkflow:
    """拍卖工作流：3 轮轮询，前 2 轮广播报价，第 3 轮 LLM 汇总。"""

    def __init__(self) -> None:
        self._quotes: list[Quote] = []
        self._status: AuctionStatus = AuctionStatus.POLLING
        self._order_id: str = ""
        self._order_status: int = 0
        self._order_status_desc: str = ""
        self._recommendation: str = ""
        self._total_merchants: int = 0
        self._round: int = 0

    @workflow.run
    async def run(self, params: AuctionParams) -> AuctionResult:
        task_id: str = workflow.info().workflow_id
        self._order_id = params.order_id

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖启动] task_id=%s | order_id=%s\n"
            "  共 %d 轮，间隔 %s 秒\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id,
            TOTAL_ROUNDS, POLL_INTERVALS,
        )

        for round_idx in range(TOTAL_ROUNDS):
            self._round = round_idx + 1
            is_last_round: bool = round_idx == TOTAL_ROUNDS - 1

            # 等待本轮间隔
            await workflow.sleep(timedelta(seconds=POLL_INTERVALS[round_idx]))

            # 轮询报价
            workflow.logger.info(
                "[第 %d/%d 轮] 轮询报价 order_id=%s",
                self._round, TOTAL_ROUNDS, params.order_id,
            )

            poll_result: PollResult = await workflow.execute_activity(
                poll_quotes_activity,
                params.order_id,
                start_to_close_timeout=timedelta(seconds=15),
            )

            self._quotes = poll_result.quotes
            self._order_status = poll_result.order_status
            self._order_status_desc = poll_result.order_status_desc

            if self._total_merchants == 0:
                self._total_merchants = len(poll_result.quotes)

            responded: list[Quote] = [q for q in self._quotes if q.offer_status > 0]
            workflow.logger.info(
                "  已报价=%d/%d | orderStatus=%d(%s)",
                len(responded), self._total_merchants,
                self._order_status, self._order_status_desc,
            )

            if is_last_round:
                # 第 3 轮：LLM 汇总
                workflow.logger.info("[第 %d 轮] 触发 LLM 汇总", self._round)
                self._recommendation = await workflow.execute_activity(
                    summarize_quotes_activity,
                    self._quotes,
                    start_to_close_timeout=timedelta(seconds=30),
                )
            else:
                # 第 1、2 轮：广播当前报价
                workflow.logger.info("[第 %d 轮] 广播当前报价给商户", self._round)
                await workflow.execute_activity(
                    broadcast_quotes_activity,
                    [params.order_id, self._quotes],
                    start_to_close_timeout=timedelta(seconds=15),
                )

        # 完成
        self._status = AuctionStatus.COMPLETED
        sorted_quotes: list[Quote] = sorted(
            [q for q in self._quotes if q.offer_status > 0],
            key=lambda q: q.offer_price,
        )

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖完成] task_id=%s | order_id=%s\n"
            "%s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id, self._recommendation,
        )

        return AuctionResult(
            task_id=task_id,
            order_id=params.order_id,
            order_status=self._order_status,
            order_status_desc=self._order_status_desc,
            status=AuctionStatus.COMPLETED,
            total_merchants=self._total_merchants,
            total_responded=len(sorted_quotes),
            quotes=sorted_quotes,
            best_offer=sorted_quotes[0] if sorted_quotes else None,
            recommendation=self._recommendation,
        )

    @workflow.query
    def get_status(self) -> dict[str, object]:
        """实时查询任务进度。"""
        responded: list[Quote] = [q for q in self._quotes if q.offer_status > 0]
        sorted_quotes: list[Quote] = sorted(responded, key=lambda q: q.offer_price)
        return {
            "status": self._status.value,
            "order_id": self._order_id,
            "order_status": self._order_status,
            "order_status_desc": self._order_status_desc,
            "round": self._round,
            "total_rounds": TOTAL_ROUNDS,
            "total_merchants": self._total_merchants,
            "total_responded": len(responded),
            "quotes": [q.model_dump() for q in sorted_quotes],
            "recommendation": self._recommendation,
        }

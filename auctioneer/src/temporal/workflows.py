"""拍卖 Workflow：定时轮询 /serviceorder/detail，收齐报价后触发汇总。"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.models import (
        AuctionParams,
        AuctionResult,
        AuctionStatus,
        OrderStatus,
        PollResult,
        Quote,
    )
    from src.temporal.activities import poll_quotes_activity, summarize_quotes_activity

# 轮询配置
POLL_INTERVAL: timedelta = timedelta(seconds=10)
MAX_DURATION: timedelta = timedelta(seconds=60)


@workflow.defn
class AuctionWorkflow:
    """拍卖工作流：定时轮询商户报价，到时间后汇总推荐。"""

    def __init__(self) -> None:
        self._quotes: list[Quote] = []
        self._status: AuctionStatus = AuctionStatus.POLLING
        self._order_id: str = ""
        self._order_status: int = OrderStatus.INQUIRING
        self._order_status_desc: str = ""
        self._recommendation: str = ""
        self._total_merchants: int = 0

    @workflow.run
    async def run(self, params: AuctionParams) -> AuctionResult:
        task_id: str = workflow.info().workflow_id
        self._order_id = params.order_id
        start = workflow.now()
        round_num: int = 0

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖启动] task_id=%s | order_id=%s\n"
            "  轮询间隔：%ds | 最大时长：%ds\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id,
            int(POLL_INTERVAL.total_seconds()),
            int(MAX_DURATION.total_seconds()),
        )

        while workflow.now() - start < MAX_DURATION:
            round_num += 1
            elapsed: float = (workflow.now() - start).total_seconds()

            workflow.logger.info(
                "[第 %d 轮轮询] elapsed=%.0fs | order_id=%s",
                round_num, elapsed, params.order_id,
            )

            poll_result: PollResult = await workflow.execute_activity(
                poll_quotes_activity,
                params.order_id,
                start_to_close_timeout=timedelta(seconds=15),
            )

            # 更新状态
            self._quotes = poll_result.quotes
            self._order_status = poll_result.order_status
            self._order_status_desc = poll_result.order_status_desc

            # 首次轮询确定商户总数
            if self._total_merchants == 0:
                self._total_merchants = len(poll_result.quotes)
                workflow.logger.info(
                    "  参与商户数：%d", self._total_merchants,
                )

            responded: list[Quote] = [q for q in self._quotes if q.offer_status > 0]
            pending_count: int = self._total_merchants - len(responded)

            workflow.logger.info(
                "  已报价=%d/%d | 待报价=%d | orderStatus=%d(%s)",
                len(responded), self._total_merchants, pending_count,
                self._order_status, self._order_status_desc,
            )

            # 终止条件 1：订单状态已不在询价中（已下单、已取消等）
            if self._order_status != OrderStatus.INQUIRING:
                workflow.logger.info(
                    "[提前结束] 订单状态已变更为 %d(%s)，停止轮询",
                    self._order_status, self._order_status_desc,
                )
                break

            # 终止条件 2：所有商户已报价
            if pending_count <= 0:
                workflow.logger.info("[提前结束] 所有商户已报价，跳过剩余等待")
                break

            remaining: float = MAX_DURATION.total_seconds() - (workflow.now() - start).total_seconds()
            workflow.logger.info(
                "[等待] 下次轮询倒计时 %ds（距结束还剩 %.0fs）",
                int(POLL_INTERVAL.total_seconds()), remaining,
            )
            await workflow.sleep(POLL_INTERVAL)

        # 触发汇总
        elapsed_total: float = (workflow.now() - start).total_seconds()
        responded_final: list[Quote] = [q for q in self._quotes if q.offer_status > 0]
        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[汇总触发] elapsed=%.0fs | %d 家已报价 | 共轮询 %d 次\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            elapsed_total, len(responded_final), round_num,
        )

        self._recommendation = await workflow.execute_activity(
            summarize_quotes_activity,
            self._quotes,
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._status = AuctionStatus.COMPLETED

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖完成] task_id=%s | order_id=%s\n"
            "%s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, params.order_id, self._recommendation,
        )

        sorted_quotes: list[Quote] = sorted(responded_final, key=lambda q: q.offer_price)
        return AuctionResult(
            task_id=task_id,
            order_id=params.order_id,
            order_status=self._order_status,
            order_status_desc=self._order_status_desc,
            status=AuctionStatus.COMPLETED,
            total_merchants=self._total_merchants,
            total_responded=len(responded_final),
            quotes=sorted_quotes,
            best_offer=sorted_quotes[0] if sorted_quotes else None,
            recommendation=self._recommendation,
        )

    @workflow.query
    def get_status(self) -> dict[str, object]:
        """实时查询任务进度（可在 workflow 运行中调用）。"""
        responded: list[Quote] = [q for q in self._quotes if q.offer_status > 0]
        sorted_quotes: list[Quote] = sorted(responded, key=lambda q: q.offer_price)
        return {
            "status": self._status.value,
            "order_id": self._order_id,
            "order_status": self._order_status,
            "order_status_desc": self._order_status_desc,
            "total_merchants": self._total_merchants,
            "total_responded": len(responded),
            "quotes": [q.model_dump() for q in sorted_quotes],
            "recommendation": self._recommendation,
        }

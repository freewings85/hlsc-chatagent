"""拍卖 Workflow：10 秒轮询一次报价，60 秒后触发汇总。"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.models import AuctionParams, AuctionResult, AuctionStatus, Quote
    from src.temporal.activities import poll_quotes_activity, summarize_quotes_activity

# Demo 配置
POLL_INTERVAL: timedelta = timedelta(seconds=10)
MAX_DURATION: timedelta = timedelta(seconds=60)
TOTAL_MERCHANTS: int = 3  # 与 activities._MOCK_MERCHANTS 数量一致


@workflow.defn
class AuctionWorkflow:
    """拍卖工作流：定时轮询商户报价，到时间后汇总推荐。"""

    def __init__(self) -> None:
        self._quotes: list[Quote] = []
        self._status: AuctionStatus = AuctionStatus.POLLING
        self._recommendation: str = ""

    @workflow.run
    async def run(self, params: AuctionParams) -> AuctionResult:
        task_id: str = workflow.info().workflow_id
        start = workflow.now()
        round_num: int = 0

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖启动] task_id=%s\n"
            "  商户数：%d | 轮询间隔：%ds | 最大时长：%ds\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, TOTAL_MERCHANTS,
            int(POLL_INTERVAL.total_seconds()),
            int(MAX_DURATION.total_seconds()),
        )

        while workflow.now() - start < MAX_DURATION:
            round_num += 1
            elapsed: float = (workflow.now() - start).total_seconds()
            responded_ids: list[str] = [q.shop_id for q in self._quotes]

            workflow.logger.info(
                "[第 %d 轮轮询] elapsed=%.0fs | 已回复=%d/%d | 待回复=%d 家",
                round_num, elapsed,
                len(responded_ids), TOTAL_MERCHANTS,
                TOTAL_MERCHANTS - len(responded_ids),
            )

            new_quotes: list[Quote] = await workflow.execute_activity(
                poll_quotes_activity,
                responded_ids,
                start_to_close_timeout=timedelta(seconds=15),
            )
            self._quotes.extend(new_quotes)

            responded_count: int = len({q.shop_id for q in self._quotes})

            if new_quotes:
                for q in new_quotes:
                    workflow.logger.info(
                        "  ✓ 新报价  %s ¥%.1f", q.shop_name, q.quote_price,
                    )
            else:
                workflow.logger.info("  - 本轮无新报价")

            workflow.logger.info(
                "  当前进度：%d/%d 家已回复", responded_count, TOTAL_MERCHANTS,
            )

            if responded_count >= TOTAL_MERCHANTS:
                workflow.logger.info("[提前结束] 所有商户已回复，跳过剩余等待")
                break

            remaining: float = MAX_DURATION.total_seconds() - (workflow.now() - start).total_seconds()
            workflow.logger.info(
                "[等待] 下次轮询倒计时 %ds（距结束还剩 %.0fs）",
                int(POLL_INTERVAL.total_seconds()), remaining,
            )
            await workflow.sleep(POLL_INTERVAL)

        # 触发汇总
        elapsed_total: float = (workflow.now() - start).total_seconds()
        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[汇总触发] elapsed=%.0fs | 共 %d 家报价 | 共轮询 %d 次\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            elapsed_total, len(self._quotes), round_num,
        )

        self._recommendation = await workflow.execute_activity(
            summarize_quotes_activity,
            self._quotes,
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._status = AuctionStatus.COMPLETED

        workflow.logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "[拍卖完成] task_id=%s\n"
            "%s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            task_id, self._recommendation,
        )

        sorted_quotes: list[Quote] = sorted(self._quotes, key=lambda q: q.quote_price)
        return AuctionResult(
            task_id=task_id,
            status=AuctionStatus.COMPLETED,
            total_merchants=TOTAL_MERCHANTS,
            total_responded=len(self._quotes),
            quotes=sorted_quotes,
            best_offer=sorted_quotes[0] if sorted_quotes else None,
            recommendation=self._recommendation,
        )

    @workflow.query
    def get_status(self) -> dict[str, object]:
        """实时查询任务进度（可在 workflow 运行中调用）。"""
        sorted_quotes: list[Quote] = sorted(self._quotes, key=lambda q: q.quote_price)
        return {
            "status": self._status.value,
            "total_merchants": TOTAL_MERCHANTS,
            "total_responded": len({q.shop_id for q in self._quotes}),
            "quotes": [q.model_dump() for q in sorted_quotes],
            "recommendation": self._recommendation,
        }

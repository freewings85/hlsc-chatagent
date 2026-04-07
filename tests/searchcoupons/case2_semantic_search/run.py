"""SC-002: 统一入口"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_TESTS_DIR: Path = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_TESTS_DIR))

from scenario_utils.cleanup import clear_all
from scenario_utils.mock_dm import start_mock_dm, stop_mock_dm
from scenario_utils.kafka_producer import send_shop_events, send_coupon_events, wait_for_consumer
from searchcoupons.case2_semantic_search.mock_data import (
    SHOPS, SHOP_EVENTS, COUPON_EVENTS, PROJECTS, QUOTATIONS,
)

_B: str = "\033[1m"
_C: str = "\033[96m"
_G: str = "\033[92m"
_R: str = "\033[91m"
_0: str = "\033[0m"


async def run() -> bool:
    print(f"\n{_C}>>> Step 1: 清理{_0}")
    clear_all()

    print(f"\n{_C}>>> Step 2: 启动 mock DM{_0}")
    stop_mock_dm()
    start_mock_dm(shops=SHOPS, projects=PROJECTS, quotations=QUOTATIONS)

    print(f"\n{_C}>>> Step 3: Seed Kafka{_0}")
    shop_count: int = send_shop_events(SHOP_EVENTS)
    coupon_count: int = send_coupon_events(COUPON_EVENTS)

    print(f"\n{_C}>>> Step 4: 等待入库{_0}")
    wait_for_consumer("shop_merchants", shop_count, timeout=30)
    wait_for_consumer("coupon_vectors", coupon_count, timeout=30)

    print(f"\n{_C}>>> Step 5: 运行测试{_0}")
    from searchcoupons.case2_semantic_search.test_case import test_semantic_search
    passed: bool = await test_semantic_search()

    print(f"\n{_C}>>> Step 6: 清理{_0}")
    stop_mock_dm()
    return passed


def main() -> None:
    print(f"\n{_B}SC-002: 语义搜索优惠 — 全流程{_0}")
    passed: bool = asyncio.run(run())
    status: str = f"{_G}PASS{_0}" if passed else f"{_R}FAIL{_0}"
    print(f"\n{_B}最终结果: {status}{_0}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

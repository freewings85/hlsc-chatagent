"""SS-002: 统一入口"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_TESTS_DIR: Path = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_TESTS_DIR))

from scenario_utils.cleanup import clear_all
from scenario_utils.mock_dm import start_mock_dm, stop_mock_dm
from scenario_utils.kafka_producer import send_shop_events, wait_for_consumer
from searchshops.case2_filter_by_type.mock_data import SHOPS, SHOP_EVENTS, PROJECTS, QUOTATIONS

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
    count: int = send_shop_events(SHOP_EVENTS)
    print(f"  已发送 {count} 条")

    print(f"\n{_C}>>> Step 4: 等待入库{_0}")
    wait_for_consumer("shop_merchants", count, timeout=30)

    print(f"\n{_C}>>> Step 5: 运行测试{_0}")
    from searchshops.case2_filter_by_type.test_case import test_filter_by_type
    passed: bool = await test_filter_by_type()

    print(f"\n{_C}>>> Step 6: 清理{_0}")
    stop_mock_dm()
    return passed


def main() -> None:
    print(f"\n{_B}{'=' * 60}{_0}")
    print(f"{_B}SS-002: 按商户类型筛选 — 全流程{_0}")
    print(f"{_B}{'=' * 60}{_0}")
    passed: bool = asyncio.run(run())
    status: str = f"{_G}PASS{_0}" if passed else f"{_R}FAIL{_0}"
    print(f"\n{_B}最终结果: {status}{_0}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

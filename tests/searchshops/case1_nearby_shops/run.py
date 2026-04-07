"""SS-001: 统一入口 — 清理 → 启动 mock DM → seed kafka → verify milvus → test

用法：
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    uv run python tests/searchshops/case1_nearby_shops/run.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# 添加 tests 目录到 sys.path
_TESTS_DIR: Path = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_TESTS_DIR))

from scenario_utils.cleanup import clear_all
from scenario_utils.mock_dm import start_mock_dm, stop_mock_dm
from scenario_utils.kafka_producer import send_shop_events, wait_for_consumer
from searchshops.case1_nearby_shops.mock_data import SHOPS, SHOP_EVENTS, PROJECTS, QUOTATIONS

_B: str = "\033[1m"
_C: str = "\033[96m"
_G: str = "\033[92m"
_R: str = "\033[91m"
_0: str = "\033[0m"


def step(name: str) -> None:
    print(f"\n{_C}>>> {name}{_0}")


async def run() -> bool:
    # Step 1: 清理
    step("Step 1: 清理 Milvus 数据")
    clear_all()

    # Step 2: 启动 mock DM
    step("Step 2: 启动 mock DM")
    stop_mock_dm()
    start_mock_dm(shops=SHOPS, projects=PROJECTS, quotations=QUOTATIONS)

    # Step 3: Seed Kafka（商户数据入 shop-consumer）
    step("Step 3: 发送 Kafka 商户事件")
    count: int = send_shop_events(SHOP_EVENTS)
    print(f"  已发送 {count} 条")

    # Step 4: 等待 consumer 入库
    step("Step 4: 等待 shop-consumer 入库")
    ok: bool = wait_for_consumer("shop_merchants", count, timeout=30)
    if not ok:
        print(f"  {_R}入库超时，继续执行测试（search_shops 走 DM 不依赖 Milvus）{_0}")

    # Step 5: 运行测试
    step("Step 5: 运行测试")
    # 动态导入避免循环
    from searchshops.case1_nearby_shops.test_case import test_nearby_shops
    passed: bool = await test_nearby_shops()

    # Step 6: 清理
    step("Step 6: 停止 mock DM")
    stop_mock_dm()

    return passed


def main() -> None:
    print(f"\n{_B}{'=' * 60}{_0}")
    print(f"{_B}SS-001: 附近门店搜索 — 全流程{_0}")
    print(f"{_B}{'=' * 60}{_0}")

    passed: bool = asyncio.run(run())

    print(f"\n{_B}{'=' * 60}{_0}")
    status: str = f"{_G}PASS{_0}" if passed else f"{_R}FAIL{_0}"
    print(f"最终结果: {status}")
    print(f"{_B}{'=' * 60}{_0}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

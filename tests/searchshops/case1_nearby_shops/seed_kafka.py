"""SS-001: 发送商户数据到 Kafka"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加 tests 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario_utils.kafka_producer import send_shop_events, wait_for_consumer
from searchshops.case1_nearby_shops.mock_data import SHOP_EVENTS


def main() -> None:
    count: int = send_shop_events(SHOP_EVENTS)
    print(f"已发送 {count} 条商户事件")

    ok: bool = wait_for_consumer("shop_merchants", count, timeout=30)
    if ok:
        print("商户数据已入库")
    else:
        print("警告：商户数据入库超时")


if __name__ == "__main__":
    main()

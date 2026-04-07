"""SS-001: 验证商户数据已入库 Milvus"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pymilvus import Collection, connections


def main() -> None:
    connections.connect(host="localhost", port="19530")
    coll: Collection = Collection("shop_merchants")
    coll.load()

    count: int = coll.num_entities
    print(f"shop_merchants 当前 entities: {count}")

    # 查询验证
    results: list[dict] = coll.query(
        expr="shop_id >= 0",
        output_fields=["shop_id", "shop_name", "city_name"],
        limit=20,
    )
    print(f"查询返回 {len(results)} 条:")
    for r in results:
        print(f"  {r['shop_id']}: {r['shop_name']} ({r['city_name']})")


if __name__ == "__main__":
    main()

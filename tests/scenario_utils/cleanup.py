"""Milvus collection 清理工具 — 清空测试数据

采用 drop + recreate 策略确保彻底清理（Milvus delete 后 num_entities 不会立即归零）。
"""

from __future__ import annotations

import time

from pymilvus import (
    Collection,
    CollectionSchema,
    FieldSchema,
    connections,
    utility,
)


def clear_milvus_collection(collection_name: str, host: str = "localhost", port: str = "19530") -> int:
    """清空指定 Milvus collection：drop + recreate（确保彻底清理）。"""
    connections.connect(host=host, port=port)

    if not utility.has_collection(collection_name):
        print(f"[cleanup] collection '{collection_name}' 不存在，跳过")
        return 0

    coll: Collection = Collection(collection_name)
    before: int = coll.num_entities

    # 保存 schema 和索引信息用于重建
    schema: CollectionSchema = coll.schema
    index_infos: list[dict] = []
    for idx in coll.indexes:
        index_infos.append({
            "field_name": idx.field_name,
            "index_params": idx.params,
        })

    # drop + recreate
    utility.drop_collection(collection_name)
    new_coll: Collection = Collection(collection_name, schema)

    # 重建索引
    for idx_info in index_infos:
        new_coll.create_index(idx_info["field_name"], idx_info["index_params"])

    new_coll.load()

    # 等待 load 完成
    time.sleep(0.5)

    print(f"[cleanup] {collection_name}: drop+recreate 完成（清除 {before} 条）")
    return before


def clear_all(host: str = "localhost", port: str = "19530") -> None:
    """清空 shop_merchants + coupon_vectors 两个 collection。"""
    clear_milvus_collection("shop_merchants", host, port)
    clear_milvus_collection("coupon_vectors", host, port)
    print("[cleanup] 全部清理完成")

"""Milvus collection 清理工具 — 清空测试数据"""

from __future__ import annotations

from pymilvus import Collection, connections, utility


def clear_milvus_collection(collection_name: str, host: str = "localhost", port: str = "19530") -> int:
    """清空指定 Milvus collection 的数据，返回清理前的 entity 数量。"""
    connections.connect(host=host, port=port)

    if not utility.has_collection(collection_name):
        print(f"[cleanup] collection '{collection_name}' 不存在，跳过")
        return 0

    coll: Collection = Collection(collection_name)
    coll.load()
    before: int = coll.num_entities

    if before == 0:
        print(f"[cleanup] {collection_name} 已为空")
        return 0

    # 获取主键字段名
    pk_field: str = ""
    for field in coll.schema.fields:
        if field.is_primary:
            pk_field = field.name
            break

    if not pk_field:
        print(f"[cleanup] {collection_name} 找不到主键字段")
        return before

    # 删除所有数据（用 > 0 条件匹配所有正整数主键）
    coll.delete(f"{pk_field} > 0")
    coll.flush()

    after: int = coll.num_entities
    print(f"[cleanup] {collection_name}: {before} -> {after} entities")
    return before


def clear_all(host: str = "localhost", port: str = "19530") -> None:
    """清空 shop_merchants + coupon_vectors 两个 collection。"""
    clear_milvus_collection("shop_merchants", host, port)
    clear_milvus_collection("coupon_vectors", host, port)
    print("[cleanup] 全部清理完成")

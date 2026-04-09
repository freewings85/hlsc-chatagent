"""端到端测试：从 Kafka 读数据 → embedding → 写 Milvus → 搜索验证。

模拟 shop consumer 和 coupon consumer 的完整流程。
"""

import json
import httpx
from kafka import KafkaConsumer
from pymilvus import connections, Collection

# ---- 配置 ----
KAFKA_BOOTSTRAP: str = "192.168.100.108:9092"
EMBEDDING_URL: str = "http://192.168.70.17:7683/v1/embeddings"
EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
MILVUS_HOST: str = "localhost"
MILVUS_PORT: int = 19530

SHOP_TOPIC: str = "shop-sync"
COUPON_TOPIC: str = "commercial-activity-rag"
SHOP_COLLECTION: str = "shop_merchants"
COUPON_COLLECTION: str = "coupon_vectors"


def embed(text: str) -> list[float]:
    if not text:
        text = "空"
    resp = httpx.post(EMBEDDING_URL, json={"model": EMBEDDING_MODEL, "input": text}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def consume_shops(max_messages: int = 20) -> None:
    print(f"\n{'='*60}")
    print(f"消费 shop-sync topic（最多 {max_messages} 条）")
    print(f"{'='*60}")

    consumer = KafkaConsumer(
        SHOP_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset='earliest',
        consumer_timeout_ms=10000,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    col = Collection(SHOP_COLLECTION)

    count: int = 0
    for msg in consumer:
        if count >= max_messages:
            break
        event = msg.value

        shop_id: int = event.get("commercialId", 0)
        name: str = event.get("commercialName", "")
        short_name: str = event.get("shortName", "")
        province: str = event.get("provinceName", "")
        city: str = event.get("cityName", "")
        if city and not city.endswith("市"):
            city = city + "市"
        district: str = event.get("districtName", "")
        address: str = event.get("address", "")
        service_scope: str = event.get("serviceScope", "")
        phone: str = event.get("phone", "")
        licensing: str = event.get("licensing", "")
        specialty: str = event.get("specialty", "")
        guarantee: str = event.get("guarantee", "")
        trading_count: float = float(event.get("tradingCount", 0) or 0)
        enable: int = int(event.get("enable", 1) or 1)
        lat: float = float(event.get("latitude", 0) or 0)
        lng: float = float(event.get("longitude", 0) or 0)
        rating: float = float(event.get("rating", 0) or 0)

        # shop_type: 名称文本 + code 数组
        raw_type_ids = event.get("commercialType") or []
        shop_type_codes: list[int] = []
        for t in raw_type_ids:
            try:
                shop_type_codes.append(int(t))
            except (ValueError, TypeError):
                pass
        # 简单翻译（这里没有缓存，用 code 当名称占位）
        shop_type_str: str = ",".join(str(t) for t in shop_type_codes)

        opening_hour = event.get("openingHour") or {}
        opening_start: str = opening_hour.get("starTime", "") or ""
        opening_end: str = opening_hour.get("endTime", "") or ""

        # embedding
        address_text: str = f"{province}{city}{district}{address}"
        name_vec = embed(name)
        scope_vec = embed(service_scope or "无")
        addr_vec = embed(address_text or "未知地址")

        # 截断函数
        def trunc(s: str, max_bytes: int) -> str:
            b = s.encode('utf-8')
            if len(b) <= max_bytes:
                return s
            result = ""
            byte_count = 0
            for ch in s:
                ch_bytes = len(ch.encode('utf-8'))
                if byte_count + ch_bytes > max_bytes:
                    break
                result += ch
                byte_count += ch_bytes
            return result

        data = [{
            "shop_id": shop_id,
            "shop_name": name[:256] if name else "",
            "shop_type": trunc(shop_type_str, 512),
            "shop_type_codes": shop_type_codes,
            "province": trunc(province, 64),
            "city_name": trunc(city, 64),
            "district": trunc(district, 64),
            "address": trunc(address, 512),
            "service_scope": trunc(service_scope, 2048),
            "phone": trunc(phone, 64),
            "short_name": short_name[:128] if short_name else "",
            "licensing": trunc(licensing, 2048),
            "specialty": trunc(specialty, 2048),
            "guarantee": trunc(guarantee, 2048),
            "trading_count": trading_count,
            "enable": enable,
            "opening_start": opening_start[:8],
            "opening_end": opening_end[:8],
            "shop_lat": lat,
            "shop_lng": lng,
            "rating": rating,
            "name_vector": name_vec,
            "scope_vector": scope_vec,
            "address_vector": addr_vec,
        }]

        col.insert(data)
        count += 1
        print(f"  [{count}] shop_id={shop_id}, name={name}, type_codes={shop_type_codes}, city={city}")

    col.flush()
    print(f"\n写入完成: {count} 条商户, collection={SHOP_COLLECTION}, entities={col.num_entities}")
    consumer.close()
    connections.disconnect("default")


def consume_coupons(max_messages: int = 20) -> None:
    print(f"\n{'='*60}")
    print(f"消费 commercial-activity-rag topic（最多 {max_messages} 条）")
    print(f"{'='*60}")

    consumer = KafkaConsumer(
        COUPON_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset='earliest',
        consumer_timeout_ms=10000,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    col = Collection(COUPON_COLLECTION)

    count: int = 0
    for msg in consumer:
        if count >= max_messages:
            break
        event = msg.value

        activity_id: int = event.get("activityId", 0)
        commercial_id: int = event.get("commercialId", 0)
        package_id: int = event.get("packageId", 0)
        package_name: str = event.get("packageName", "") or ""
        content: str = event.get("content", "") or ""
        description: str = event.get("description", "") or ""
        promo_value: float = float(event.get("promoValue", 0) or 0)
        relative_amount: float = float(event.get("relativeAmount", 0) or 0)

        # discountType → codes + 名称占位
        raw_discount_types = event.get("discountType") or []
        activity_category_codes: list[int] = []
        for t in raw_discount_types:
            try:
                activity_category_codes.append(int(t))
            except (ValueError, TypeError):
                pass
        activity_category_str: str = ",".join(str(t) for t in activity_category_codes)

        # 时间
        import datetime
        def parse_time(s: str) -> int:
            if not s:
                return 0
            try:
                dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                return int(dt.timestamp() * 1000)
            except Exception:
                return 0

        start_time_ms: int = parse_time(event.get("startTime", ""))
        end_time_ms: int = parse_time(event.get("endTime", ""))

        # 商户信息（简化，不调 getShopById）
        commercial_name: str = ""
        shop_lat: float = 0.0
        shop_lng: float = 0.0
        province: str = ""
        city_name: str = ""
        district_name: str = ""
        address: str = ""
        phone: str = ""
        rating: float = 0.0
        service_scope: str = ""
        opening_hours: str = ""

        # embedding
        content_vec = embed(content or "无")
        desc_vec = embed(description[:500] if description else "无")
        address_text: str = f"{province}{city_name}{district_name}{address}"
        addr_vec = embed(address_text or "未知地址")

        def trunc(s: str, max_bytes: int) -> str:
            b = s.encode('utf-8')
            if len(b) <= max_bytes:
                return s
            result = ""
            byte_count = 0
            for ch in s:
                ch_bytes = len(ch.encode('utf-8'))
                if byte_count + ch_bytes > max_bytes:
                    break
                result += ch
                byte_count += ch_bytes
            return result

        data = [{
            "activity_id": activity_id,
            "commercial_id": commercial_id,
            "project_id": package_id,
            "project_name": package_name[:128],
            "activity_category": trunc(activity_category_str, 256),
            "activity_category_codes": activity_category_codes,
            "start_time": start_time_ms,
            "end_time": end_time_ms,
            "relative_amount": relative_amount,
            "promo_value": promo_value,
            "content": content[:512] if content else "",
            "description": trunc(description, 2048),
            "commercial_name": commercial_name,
            "shop_lat": shop_lat,
            "shop_lng": shop_lng,
            "province": province,
            "city_name": city_name,
            "district": district_name,
            "address": address,
            "phone": phone,
            "rating": rating,
            "service_scope": service_scope,
            "opening_hours": opening_hours,
            "content_vector": content_vec,
            "description_vector": desc_vec,
            "address_vector": addr_vec,
        }]

        col.insert(data)
        count += 1
        print(f"  [{count}] activity_id={activity_id}, content={content[:30]}, type_codes={activity_category_codes}")

    col.flush()
    print(f"\n写入完成: {count} 条优惠, collection={COUPON_COLLECTION}, entities={col.num_entities}")
    consumer.close()
    connections.disconnect("default")


def test_search() -> None:
    print(f"\n{'='*60}")
    print("搜索测试")
    print(f"{'='*60}")

    from pymilvus import AnnSearchRequest, RRFRanker

    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

    # 测试 shop 搜索
    shop_col = Collection(SHOP_COLLECTION)
    shop_col.load()
    print(f"\nshop_merchants: {shop_col.num_entities} entities")

    if shop_col.num_entities > 0:
        # 简单 query 验证 shop_type_codes 字段
        results = shop_col.query(
            expr="shop_id > 0",
            output_fields=["shop_id", "shop_name", "shop_type", "shop_type_codes", "city_name", "district"],
            limit=5,
        )
        print("\nShop 数据样本:")
        for r in results:
            print(f"  id={r['shop_id']}, name={r['shop_name']}, type={r['shop_type']}, codes={r['shop_type_codes']}, city={r['city_name']}")

    # 测试 coupon 搜索
    coupon_col = Collection(COUPON_COLLECTION)
    coupon_col.load()
    print(f"\ncoupon_vectors: {coupon_col.num_entities} entities")

    if coupon_col.num_entities > 0:
        results = coupon_col.query(
            expr="activity_id > 0",
            output_fields=["activity_id", "content", "activity_category", "activity_category_codes", "commercial_name"],
            limit=5,
        )
        print("\nCoupon 数据样本:")
        for r in results:
            print(f"  id={r['activity_id']}, content={r['content'][:30]}, category={r['activity_category']}, codes={r['activity_category_codes']}")

    # 测试 array_contains_any 过滤
    if shop_col.num_entities > 0:
        print("\n测试 shop_type_codes array_contains_any:")
        # 获取第一条数据的 codes
        first = shop_col.query(expr="shop_id > 0", output_fields=["shop_type_codes"], limit=1)
        if first and first[0]["shop_type_codes"]:
            test_code = first[0]["shop_type_codes"][0]
            filtered = shop_col.query(
                expr=f"array_contains_any(shop_type_codes, [{test_code}])",
                output_fields=["shop_id", "shop_name", "shop_type_codes"],
                limit=5,
            )
            print(f"  filter: array_contains_any(shop_type_codes, [{test_code}])")
            print(f"  匹配: {len(filtered)} 条")
            for r in filtered:
                print(f"    id={r['shop_id']}, name={r['shop_name']}, codes={r['shop_type_codes']}")

    connections.disconnect("default")


if __name__ == "__main__":
    consume_shops(max_messages=20)
    consume_coupons(max_messages=20)
    test_search()

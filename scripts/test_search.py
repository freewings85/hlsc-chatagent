"""搜索服务测试脚本 — 验证多种查询模式（含位置过滤）"""

import httpx
import json

BASE_URL: str = "http://localhost:8091"
TIMEOUT: float = 60.0


def pretty(label: str, resp: httpx.Response) -> None:
    print(f"\n{'='*60}")
    print(f"[{label}]  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"ERROR: {resp.text}")
        return
    data: dict = resp.json()
    activities: list = data.get("result", {}).get("shopActivities", [])
    print(f"返回 {len(activities)} 条活动:")
    for a in activities:
        dist: str = f" | 距离={a['distance_km']:.1f}km" if "distance_km" in a else ""
        shop: str = f" | 商户={a.get('commercial_name')}" if a.get("commercial_name") else ""
        print(f"  - id={a.get('activity_id')} | {a.get('activity_name')} | "
              f"类别={a.get('activity_category')} | 金额={a.get('discount_amount')}"
              f"{shop}{dist}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    # 测试 0：健康检查
    resp: httpx.Response = httpx.get(f"{BASE_URL}/health")
    print(f"Health: {resp.json()}")

    # 测试 1：按项目查
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"projectIds": [5001], "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("按项目查 projectIds=[5001]", resp)

    # 测试 2：语义查询 — 支付宝
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"semanticQuery": "支付宝支付的优惠", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("语义: 支付宝支付的优惠", resp)

    # 测试 3：语义查询 — 送洗车
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"semanticQuery": "送洗车的活动", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("语义: 送洗车的活动", resp)

    # 测试 4：语义查询 — 满减
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"semanticQuery": "满减类优惠", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("语义: 满减类优惠", resp)

    # 测试 5：组合查询 — 换轮胎 + 折扣
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"projectIds": [5002], "semanticQuery": "打折的", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("组合: projectIds=[5002] + 语义='打折的'", resp)

    # 测试 6：按城市过滤 — 上海城区（商户101，活动 2001/2004/2007）
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"city": "上海城区", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("按城市: 上海城区", resp)

    # 测试 7：按城市过滤 — 莆田市（商户103，活动 2003/2005/2008）
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"city": "莆田市", "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("按城市: 莆田市", resp)

    # 测试 8：位置过滤 — 上海商户101附近5km (lat=31.62, lng=121.40)
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={"latitude": 31.62, "longitude": 121.40, "radius": 5.0, "topK": 5},
        timeout=TIMEOUT,
    )
    pretty("位置: 上海商户附近5km", resp)

    # 测试 9：位置 + 语义组合 — 上海附近满减优惠
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={
            "latitude": 31.62, "longitude": 121.40, "radius": 10.0,
            "semanticQuery": "满减优惠", "topK": 5,
        },
        timeout=TIMEOUT,
    )
    pretty("组合: 上海附近10km + 语义='满减优惠'", resp)

    # 测试 10：城市 + 项目 + 语义
    resp = httpx.post(
        f"{BASE_URL}/api/coupon/search",
        json={
            "city": "上海城区", "projectIds": [5001],
            "semanticQuery": "满减", "topK": 5,
        },
        timeout=TIMEOUT,
    )
    pretty("组合: 上海城区 + projectIds=[5001] + 语义='满减'", resp)


if __name__ == "__main__":
    main()

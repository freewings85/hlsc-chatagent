#!/usr/bin/env python3
"""验证 mock 数据的有效性和完整性。

运行此脚本检查：
1. mock_coupons.py 数据结构是否完整
2. search_coupon 工具是否能正确加载 mock 数据
3. apply_coupon 工具是否能生成正确的联系单

用法：
    uv run python verify_mock_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

def check_mock_coupons() -> bool:
    """验证 mock_coupons.py 中的数据结构。"""
    print("=" * 60)
    print("检查 1: Mock 优惠数据结构")
    print("=" * 60)

    try:
        from data.mock_coupons import (
            COUPONS_WITH_BOTH,
            COUPONS_PLATFORM_ONLY,
            COUPONS_EMPTY,
            COUPONS_EXPIRING_SOON,
            COUPONS_BY_DISCOUNT_AMOUNT,
        )
        print("✓ 成功导入所有 mock 数据")

        # 检查结构
        scenarios = {
            "COUPONS_WITH_BOTH": COUPONS_WITH_BOTH,
            "COUPONS_PLATFORM_ONLY": COUPONS_PLATFORM_ONLY,
            "COUPONS_EMPTY": COUPONS_EMPTY,
            "COUPONS_EXPIRING_SOON": COUPONS_EXPIRING_SOON,
            "COUPONS_BY_DISCOUNT_AMOUNT": COUPONS_BY_DISCOUNT_AMOUNT,
        }

        for name, data in scenarios.items():
            assert data.get("status") == 0, f"{name}: status 不为 0"
            assert "result" in data, f"{name}: 缺少 result 字段"
            assert "platformActivities" in data["result"], f"{name}: 缺少 platformActivities"
            assert "shopActivities" in data["result"], f"{name}: 缺少 shopActivities"

            platform_count = len(data["result"]["platformActivities"])
            shop_count = len(data["result"]["shopActivities"])
            print(f"  {name}:")
            print(f"    - 平台优惠: {platform_count} 条")
            print(f"    - 商户优惠: {shop_count} 条")

        print("✓ 所有数据结构验证通过\n")
        return True

    except Exception as e:
        print(f"✗ 错误: {e}\n")
        return False


def check_search_coupon_mock() -> bool:
    """验证 search_coupon 的 mock 模式。"""
    print("=" * 60)
    print("检查 2: search_coupon 工具 mock 模式")
    print("=" * 60)

    try:
        # 检查是否能导入
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "extensions"))
        from hlsc.tools.search_coupon import _MOCK_ENABLED, _get_mock_data

        print(f"✓ 成功导入 search_coupon 工具")
        print(f"  Mock 模式状态: {_MOCK_ENABLED}")

        # 获取 mock 数据
        mock_data_json = _get_mock_data()
        mock_data = json.loads(mock_data_json)

        assert "platformActivities" in mock_data
        assert "shopActivities" in mock_data

        platform_count = len(mock_data["platformActivities"])
        shop_count = len(mock_data["shopActivities"])

        print(f"✓ Mock 数据加载成功:")
        print(f"  - 平台优惠: {platform_count} 条")
        print(f"  - 商户优惠: {shop_count} 条")

        # 检查必要字段
        for activity in mock_data["platformActivities"]:
            assert activity.get("activity_id"), "缺少 activity_id"
            assert activity.get("activity_name"), "缺少 activity_name"
            assert activity.get("activity_description"), "缺少 activity_description"

        for activity in mock_data["shopActivities"]:
            assert activity.get("activity_id"), "缺少 activity_id"
            assert activity.get("activity_name"), "缺少 activity_name"
            assert activity.get("shop_id"), "缺少 shop_id"
            assert activity.get("shop_name"), "缺少 shop_name"
            assert activity.get("activity_description"), "缺少 activity_description"

        print("✓ 所有必要字段验证通过\n")
        return True

    except Exception as e:
        print(f"✗ 错误: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_apply_coupon_mock() -> bool:
    """验证 apply_coupon 的 mock 模式。"""
    print("=" * 60)
    print("检查 3: apply_coupon 工具 mock 模式")
    print("=" * 60)

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "extensions"))
        from hlsc.tools.apply_coupon import _MOCK_ENABLED, _get_mock_apply_result

        print(f"✓ 成功导入 apply_coupon 工具")
        print(f"  Mock 模式状态: {_MOCK_ENABLED}")

        # 生成 mock 申领结果
        result_json = _get_mock_apply_result(
            activity_id="2001",
            shop_id="101",
            visit_time="2026-04-03 14:00"
        )
        result = json.loads(result_json)

        assert result.get("status") == "success"
        assert result.get("contact_order_id")
        assert result.get("shop_name")
        assert result.get("activity_name")
        assert result.get("visit_time")
        assert result.get("message")

        print(f"✓ Mock 联系单生成成功:")
        print(f"  - 订单号: {result['contact_order_id']}")
        print(f"  - 商户: {result['shop_name']}")
        print(f"  - 活动: {result['activity_name']}")
        print(f"  - 到店时间: {result['visit_time']}")
        print()
        return True

    except Exception as e:
        print(f"✗ 错误: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    """主验证流程。"""
    print("\n" + "=" * 60)
    print("Mock 数据验证工具")
    print("=" * 60 + "\n")

    results = []

    # 运行所有检查
    results.append(check_mock_coupons())
    results.append(check_search_coupon_mock())
    results.append(check_apply_coupon_mock())

    # 总结
    print("=" * 60)
    print("验证总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✓ 全部通过 ({passed}/{total})")
        print("\n🎉 Mock 数据已就绪，可以启动 mainagent 进行测试")
        return 0
    else:
        print(f"✗ 部分失败 ({passed}/{total})")
        print("\n❌ 请修复上述问题后重试")
        return 1


if __name__ == "__main__":
    sys.exit(main())

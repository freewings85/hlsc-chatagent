"""查找本市所有保险公司 shop ids — 独立 CLI 脚本，通过 bash 工具执行。

流程：
    1. 根据 user_id 调用 getUserById 获取 cityId
    2. 根据 cityId + project_id 搜索本市所有保险公司商户

用法：
    python search_insurance_company.py --project_id 1461
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

import httpx

_logger: logging.Logger = logging.getLogger(__name__)

SERVICE_OWNER_URL: str = os.getenv("SERVICE_OWNER_URL", "")
DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


# ── 核心逻辑 ─────────────────────────────────────────────────────────────


def get_user_city_id(user_id: int) -> int:
    """调用 getUserById 获取用户所在城市 ID。"""
    url: str = f"{SERVICE_OWNER_URL}/user/getUserById"
    payload: dict[str, int] = {"userId": user_id}
    resp: httpx.Response = httpx.post(url, json=payload, timeout=10.0)
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("status") == 0:
        city_id: int | None = data.get("result", {}).get("cityId")
        if city_id is None:
            raise RuntimeError(f"用户 {user_id} 无 cityId 信息")
        return city_id
    raise RuntimeError(f"获取用户信息失败: {data.get('message', '未知错误')}")


def search_shops_by_city(
    city_id: int,
    package_ids: list[int],
    top: int = 100,
) -> list[dict]:
    """根据 cityId + packageIds 搜索本市所有保险公司商户。"""
    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getNearbyShops"
    payload: dict[str, object] = {
        "cityId": city_id,
        "top": top,
        "orderBy": "distance",
        "packageIds": package_ids,
    }
    resp: httpx.Response = httpx.post(url, json=payload, timeout=15.0)
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("status") == 0:
        return data.get("result", {}).get("commercials", [])
    raise RuntimeError(f"搜索保险公司失败: {data.get('message', '未知错误')}")


# ── 入口 ─────────────────────────────────────────────────────────────────


async def main(*, project_id: int) -> str:
    """查找本市所有保险公司 shop ids。

    owner_id 从环境变量 OWNER_ID 读取（由 bash 工具自动注入）。
    """
    if not project_id:
        return "缺少必要参数：project_id 不能为空"

    owner_id: str = os.getenv("OWNER_ID", "")
    if not owner_id:
        return "缺少 OWNER_ID 环境变量"

    try:
        city_id: int = get_user_city_id(int(owner_id))
    except Exception as e:
        return f"获取用户城市信息失败：{e}"

    try:
        commercials: list[dict] = search_shops_by_city(city_id, [project_id])
    except Exception as e:
        return f"搜索保险公司失败：{e}"

    if not commercials:
        return "本市未找到提供该项目的保险公司"

    shop_ids: list[int] = [c["commercialId"] for c in commercials if "commercialId" in c]
    shop_names: list[str] = [c.get("commercialName", "") for c in commercials if "commercialId" in c]

    result: dict[str, object] = {
        "city_id": city_id,
        "shop_ids": shop_ids,
        "total": len(shop_ids),
        "shops": [
            {"shop_id": c.get("commercialId"), "name": c.get("commercialName", "")}
            for c in commercials
            if "commercialId" in c
        ],
    }
    return json.dumps(result, ensure_ascii=False)


# ── CLI ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="查找本市所有保险公司 shop ids",
    )
    parser.add_argument("--project_id", required=True, type=int, help="项目 ID")
    args: argparse.Namespace = parser.parse_args()

    output: str = asyncio.run(main(project_id=args.project_id))
    print(output)
    sys.exit(0)

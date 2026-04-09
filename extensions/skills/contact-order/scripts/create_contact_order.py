"""生成联系单 — 独立 CLI 脚本，通过 bash 工具执行。

用法：
    python create_contact_order.py --shop_id 123 --shop_name "XX修理厂" --visit_time "明天下午" --task_describe "想换轮胎，偏好米其林"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import httpx

logging.basicConfig(level=logging.INFO)
_logger: logging.Logger = logging.getLogger(__name__)

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


def submit_contact_order(
    conversation_id: str,
    shop_id: int,
    visit_time: str,
    task_describe: str = "",
    car_key: str = "",
) -> dict:
    """调用 POST /service_ai_datamanager/task/submit 生成联系单。"""
    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/task/submit"
    payload: dict[str, object] = {
        "conversationId": conversation_id,
        "orderType": "contact",
        "appointmentTime": visit_time,
        "taskDescribe": task_describe,
        "carKey": car_key,
        "couponId": 0,
        "commercialList": [shop_id],
    }
    _logger.info("[CONTACT_ORDER] POST %s payload=%s", url, json.dumps(payload, ensure_ascii=False))
    resp: httpx.Response = httpx.post(url, json=payload, timeout=15.0)
    _logger.info("[CONTACT_ORDER] status_code=%d body=%s", resp.status_code, resp.text)
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("status") == 0:
        return data.get("result", {})
    raise RuntimeError(f"生成联系单失败: {data.get('message', '未知错误')}")


def build_order_card(result: dict, shop_name: str, visit_time: str) -> str:
    """构建 ContactOrderCard 卡片文本。"""
    order_id: str = str(result.get("taskId", ""))
    card: dict = {
        "type": "ContactOrderCard",
        "props": {
            "order_id": order_id,
            "shop_name": shop_name,
            "visit_time": visit_time,
        },
    }
    card_json: str = json.dumps(card, ensure_ascii=False)
    return (
        f"```spec\n{card_json}\n```\n"
        f"已帮您生成联系单，{shop_name}会主动联系您确认细节。"
    )


def main(
    *,
    shop_id: int,
    shop_name: str,
    visit_time: str,
    task_describe: str = "",
) -> str:
    """生成联系单，返回 ContactOrderCard。

    conversation_id 和 car_key 从环境变量读取（由 bash 工具自动注入）。
    """
    if not shop_id:
        return "缺少必要参数：shop_id 不能为空"

    if not DATA_MANAGER_URL:
        return "缺少 DATA_MANAGER_URL 环境变量，无法生成联系单"

    conversation_id: str = os.getenv("CONVERSATION_ID", "")
    car_key: str = os.getenv("CAR_MODEL_ID", "")

    try:
        result: dict = submit_contact_order(
            conversation_id=conversation_id,
            shop_id=shop_id,
            visit_time=visit_time,
            task_describe=task_describe,
            car_key=car_key,
        )
    except Exception as e:
        return f"生成联系单失败：{e}"

    return build_order_card(result, shop_name, visit_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成联系单")
    parser.add_argument("--shop_id", required=True, type=int, help="商户 ID")
    parser.add_argument("--shop_name", required=True, help="商户名称")
    parser.add_argument("--visit_time", required=True, help="预计到店时间")
    parser.add_argument("--task_describe", default="", help="用户需求描述")
    args = parser.parse_args()

    output: str = main(
        shop_id=args.shop_id,
        shop_name=args.shop_name,
        visit_time=args.visit_time,
        task_describe=args.task_describe,
    )
    print(output)
    sys.exit(0)

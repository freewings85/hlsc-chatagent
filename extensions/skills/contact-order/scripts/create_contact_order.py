"""生成联系单 — 独立 CLI 脚本，通过 bash 工具执行。

用法：
    python create_contact_order.py --shop_id 123 --project_id 1200 --task_describe "想换轮胎，偏好米其林"
    python create_contact_order.py --shop_id 123 --project_id 1200 --task_describe "小保养" --car_model_id mmu_9390
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
    project_id: int,
    task_describe: str = "",
    car_key: str = "",
) -> dict:
    """调用 POST /service_ai_datamanager/task/submit 生成联系单。"""
    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/task/submit"
    payload: dict[str, object] = {
        "conversationId": conversation_id,
        "orderType": "contact",
        "taskDescribe": task_describe,
        "carKey": car_key,
        "packageList": [project_id],
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


def format_result(result: dict) -> str:
    """返回 order_id。"""
    order_id: str = str(result.get("taskId", ""))
    return f"联系单已生成，order_id={order_id}"


def main(
    *,
    shop_id: int,
    project_id: int,
    task_describe: str = "",
    car_model_id: str = "",
) -> str:
    """生成联系单，返回 ContactOrderCard。

    conversation_id 从环境变量 CONVERSATION_ID 读取（由 bash 工具自动注入）。
    """
    if not shop_id:
        return "缺少必要参数：shop_id 不能为空"
    if not project_id:
        return "缺少必要参数：project_id 不能为空"

    if not DATA_MANAGER_URL:
        return "缺少 DATA_MANAGER_URL 环境变量，无法生成联系单"

    conversation_id: str = os.getenv("CONVERSATION_ID", "")

    try:
        result: dict = submit_contact_order(
            conversation_id=conversation_id,
            shop_id=shop_id,
            project_id=project_id,
            task_describe=task_describe,
            car_key=car_model_id,
        )
    except Exception as e:
        return f"生成联系单失败：{e}"

    return format_result(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成联系单")
    parser.add_argument("--shop_id", required=True, type=int, help="商户 ID")
    parser.add_argument("--project_id", required=True, type=int, help="项目 ID")
    parser.add_argument("--task_describe", required=True, help="用户需求描述")
    parser.add_argument("--car_model_id", default="", help="车型 key（可选）")
    args = parser.parse_args()

    output: str = main(
        shop_id=args.shop_id,
        project_id=args.project_id,
        task_describe=args.task_describe,
        car_model_id=args.car_model_id,
    )
    print(output)
    sys.exit(0)

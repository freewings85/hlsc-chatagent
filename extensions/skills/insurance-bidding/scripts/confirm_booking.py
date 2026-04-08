"""发送确认卡片并返回用户回复 — 通过 __INTERRUPT__ 协议与 agent 交互。

用法：
    python confirm_booking.py --project_id 123 --shop_ids 87,88 --car_model_id 56

流程：
    1. 输出 __INTERRUPT__:{confirm_booking 数据} 触发前端确认卡片
    2. input() 阻塞等待用户回复（agent 的 bash 工具写入 stdin）
    3. 返回用户原始回复文本，由 LLM 判断意图
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
_logger: logging.Logger = logging.getLogger("confirm_booking")


def _as_int_list(value: str) -> list[int]:
    """逗号分隔字符串 → int list。如 "87,88" → [87, 88]"""
    if not value or not value.strip():
        return []
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def main(
    *,
    project_id: int,
    shop_ids: list[int],
    car_model_id: str,
    remark: str = "",
) -> str:
    """发送确认卡片，返回用户回复。"""
    if not project_id or not shop_ids:
        return "缺少必要参数：project_id 和 shop_ids 不能为空"

    interrupt_data: dict[str, object] = {
        "type": "confirm_booking",
        "question": "请确认以下预订信息：",
        "booking_params": {
            "plan_mode": "bidding",
            "project_ids": [project_id],
            "shop_ids": shop_ids,
            "car_model_id": car_model_id,
            "booking_time": "",
            "remark": remark
        },
    }

    # 触发中断协议
    interrupt_json: str = json.dumps(interrupt_data, ensure_ascii=False)
    _logger.info("[INTERRUPT_SEND] %s", interrupt_json)
    print(f"__INTERRUPT__:{interrupt_json}", flush=True)

    # 阻塞等待用户回复
    _logger.info("[INTERRUPT_WAIT] 等待用户回复...")
    reply: str = input()
    _logger.info("[INTERRUPT_RECV] 原始回复: %s", repr(reply))

    # 解析回复（可能是 JSON 格式）
    try:
        data: dict = json.loads(reply)
        user_msg: str = str(data.get("user_msg", "")).strip()
        reply = user_msg if user_msg else reply
        _logger.info("[INTERRUPT_PARSE] JSON 解析成功, user_msg=%s", repr(user_msg))
    except (json.JSONDecodeError, AttributeError):
        reply = reply.strip()
        _logger.info("[INTERRUPT_PARSE] 纯文本回复: %s", repr(reply))

    # 将已确认参数附带返回，避免 LLM 重构参数时漂移
    shop_ids_str: str = ",".join(str(s) for s in shop_ids)
    confirmed_params: str = (
        f"--project_id {project_id} --shop_ids {shop_ids_str} --car_model_id {car_model_id}"
    )
    if remark:
        confirmed_params += f' --remark "{remark}"'
    result: str = (
        f"用户回复：{reply}\n"
        f"已确认参数：{confirmed_params}\n"
        f"请根据回复判断意图，确认则使用上述参数执行 create_order.py（不要修改参数），取消则告知车主。"
    )
    _logger.info("[INTERRUPT_RESULT] 返回给 LLM: %s", result)
    return result


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="发送确认卡片")
    parser.add_argument("--project_id", required=True, type=int, help="项目 ID")
    parser.add_argument("--shop_ids", required=True, help="商户 ID，逗号分隔")
    parser.add_argument("--car_model_id", required=True, help="车型 ID")
    parser.add_argument("--remark", default="", help="备注信息")
    args: argparse.Namespace = parser.parse_args()

    output: str = main(
        project_id=args.project_id,
        shop_ids=_as_int_list(args.shop_ids),
        car_model_id=args.car_model_id,
        remark=args.remark,
    )
    print(output)
    sys.exit(0)

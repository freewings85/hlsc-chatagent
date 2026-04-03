"""确认竞标信息 + 创建订单 — 通过 __INTERRUPT__ 协议与 agent 交互。

用法：
    python confirm_and_create.py --project_id 1461 --shop_ids 87,88 --car_model_id 56

流程：
    1. 输出 __INTERRUPT__:{confirm_booking 数据} 触发前端确认卡片
    2. input() 阻塞等待用户回复（agent 的 bash 工具写入 stdin）
    3. 判断回复意图：确认 → 创建订单 / 取消 → 结束 / 其他 → 返回给 LLM
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# ── 常量 ─────────────────────────────────────────────────────────────────

_CONFIRM_KEYWORDS: list[str] = ["确认", "没问题", "可以", "好的", "发布", "下单", "ok", "OK", "是"]
_CANCEL_KEYWORDS: list[str] = ["不用了", "算了", "取消", "不要了", "放弃"]


# ── 参数工具 ─────────────────────────────────────────────────────────────


def _as_int_list(value: str) -> list[int]:
    """逗号分隔字符串 → int list。如 "87,88" → [87, 88]"""
    if not value or not value.strip():
        return []
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def _judge_reply(reply: str) -> str:
    """判断用户回复意图：confirm / cancel / other。"""
    text: str = reply.strip()
    if any(kw in text for kw in _CONFIRM_KEYWORDS):
        return "confirm"
    if any(kw in text for kw in _CANCEL_KEYWORDS):
        return "cancel"
    return "other"


# ── 核心逻辑 ─────────────────────────────────────────────────────────────


def _send_interrupt(
    project_id: int,
    shop_ids: list[int],
    car_model_id: str,
    booking_time: str,
    remark: str,
) -> str:
    """输出 __INTERRUPT__ 标记触发确认卡片，阻塞等待用户回复。"""
    interrupt_data: dict[str, object] = {
        "type": "confirm_booking",
        "question": "请确认以下预订信息：",
        "booking_params": {
            "plan_mode": "bidding",
            "project_ids": [project_id],
            "shop_ids": shop_ids,
            "car_model_id": car_model_id,
            "booking_time": booking_time,
            "upload_image": True,
        },
    }
    if remark:
        interrupt_data["booking_params"]["remark"] = remark  # type: ignore[index]

    # 触发中断协议
    print(f"__INTERRUPT__:{json.dumps(interrupt_data, ensure_ascii=False)}", flush=True)

    # 阻塞等待 agent 写入回复
    reply: str = input()

    # 解析回复（可能是 JSON 格式）
    try:
        data: dict = json.loads(reply)
        user_msg: str = str(data.get("user_msg", "")).strip()
        return user_msg if user_msg else reply
    except (json.JSONDecodeError, AttributeError):
        return reply.strip()


async def main(
    *,
    project_id: int,
    shop_ids: list[int],
    car_model_id: str,
    booking_time: str = "由商户排期",
    remark: str = "",
) -> str:
    """确认预订信息 + 创建订单，返回结果。"""
    if not project_id or not shop_ids:
        return "缺少必要参数：project_id 和 shop_ids 不能为空"

    # 1. 发送确认卡片，等待用户回复
    reply: str = _send_interrupt(project_id, shop_ids, car_model_id, booking_time, remark)

    # 2. 判断回复意图
    intent: str = _judge_reply(reply)

    if intent == "cancel":
        return "车主已取消竞标预订。"

    if intent == "other":
        return f"车主回复：{reply}。请根据回复内容判断是否需要调整参数后重新发起。"

    # 3. 确认 → 创建订单
    from create_order import build_order_card, create_order, start_auction

    owner_id: str = os.getenv("OWNER_ID", "")
    conversation_id: str = os.getenv("CONVERSATION_ID", "")

    try:
        result: dict = create_order(
            owner_id=owner_id,
            conversation_id=conversation_id,
            package_list=[project_id],
            commercial_list=shop_ids,
            remark=remark,
        )
    except Exception as e:
        return f"创建订单失败：{e}"

    order_id: str = str(result.get("orderId", ""))

    try:
        await start_auction(order_id, conversation_id)
    except Exception:
        pass  # fire-and-forget

    return build_order_card(result)


# ── CLI ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="确认竞标信息 + 创建订单")
    parser.add_argument("--project_id", required=True, type=int, help="项目 ID")
    parser.add_argument("--shop_ids", required=True, help="商户 ID，逗号分隔")
    parser.add_argument("--car_model_id", required=True, help="车型 ID")
    parser.add_argument("--booking_time", default="由商户排期", help="到店时间")
    parser.add_argument("--remark", default="", help="备注信息")
    args: argparse.Namespace = parser.parse_args()

    output: str = asyncio.run(main(
        project_id=args.project_id,
        shop_ids=_as_int_list(args.shop_ids),
        car_model_id=args.car_model_id,
        booking_time=args.booking_time,
        remark=args.remark,
    ))
    print(output)
    sys.exit(0)

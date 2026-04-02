"""insurance-bidding SkillScript：确认竞标信息 → 创建订单 → 返回卡片。

LLM 调用示例：
    invoke_skill("insurance-bidding", args='{"project_ids":[1461],"shop_ids":[87,88],"car_model_id":"bmw-325li-2024","booking_time":"这周末"}')
"""

from __future__ import annotations

import json
from typing import Any

from agent_sdk._agent.skills.script import SkillContext, SkillScript

# 判断用户回复意图的关键词
_CONFIRM_KEYWORDS: list[str] = ["确认", "没问题", "可以", "好的", "发布", "下单", "ok", "OK"]
_CANCEL_KEYWORDS: list[str] = ["不用了", "算了", "取消", "不要了", "放弃"]


def _parse_args(raw: str) -> dict[str, Any]:
    """解析 LLM 传入的 JSON 参数。"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _judge_reply(reply: str) -> str:
    """判断用户回复意图：confirm / cancel / other。"""
    text: str = reply.strip()
    if any(kw in text for kw in _CONFIRM_KEYWORDS):
        return "confirm"
    if any(kw in text for kw in _CANCEL_KEYWORDS):
        return "cancel"
    return "other"


class InsuranceBiddingScript(SkillScript):
    """保险竞标预订脚本：confirm_booking 中断 + 创建订单。"""

    name: str = "insurance-bidding"

    async def run(self, ctx: SkillContext) -> str:
        # ── 1. 解析参数 ──────────────────────────────────────────
        params: dict[str, Any] = _parse_args(ctx.state.get("args", ""))
        project_ids: list[int] = params.get("project_ids", [])
        shop_ids: list[int] = params.get("shop_ids", [])
        car_model_id: str = params.get("car_model_id", "")
        booking_time: str = params.get("booking_time", "")

        if not project_ids or not shop_ids:
            return "缺少必要参数：project_ids 和 shop_ids 不能为空"

        deps = ctx._run_context.deps  # type: ignore[union-attr]
        owner_id: str = deps.user_id
        conversation_id: str = deps.session_id

        # ── 2. confirm_booking 中断 ─────────────────────────────
        booking_params: dict[str, object] = {
            "plan_mode": "bidding",
            "project_ids": project_ids,
            "shop_ids": shop_ids,
            "car_model_id": car_model_id,
            "booking_time": booking_time,
            "upload_image": True,
        }

        reply: str = await ctx.interrupt({
            "type": "confirm_booking",
            "question": "请确认以下预订信息：",
            "booking_params": booking_params,
        })

        # ── 3. 判断用户回复 ──────────────────────────────────────
        intent: str = _judge_reply(reply)

        if intent == "cancel":
            return "车主已取消竞标预订。"

        if intent == "other":
            return f"车主回复：{reply}。请根据回复内容判断是否需要调整参数后重新发起。"

        # ── 4. 确认 → 创建订单 ───────────────────────────────────
        from create_order import build_order_card, create_order

        try:
            result: dict = create_order(
                owner_id=owner_id,
                conversation_id=conversation_id,
                package_list=project_ids,
                commercial_list=shop_ids,
                demand=booking_time,
            )
            return build_order_card(result)

        except Exception as e:
            return f"创建订单失败：{e}"

"""卡片解析器：从工具返回文本中提取 <!--card:type--> 块。

工具返回格式：
    <!--card:repair_shops-->
    {"total": 3, "items": [...]}
    <!--/card-->
    找到 3 家修理厂，推荐评分最高的...

解析后返回 card_type、JSON 数据和 tool_call_id（由调用方注入）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

_CARD_PATTERN = re.compile(
    r"<!--card:([\w-]+)-->\s*(.*?)\s*<!--/card-->",
    re.DOTALL,
)

CARD_REMINDER_TEMPLATE = (
    "\n<system-reminder>"
    "已生成卡片数据(card:{tool_call_id})，"
    "可在回复中通过 {{{{card:{tool_call_id}}}}} 进行展示。"
    "</system-reminder>"
)


@dataclass
class CardBlock:
    """从工具返回文本中解析出的卡片块。"""

    card_type: str
    data: Any  # parsed JSON


def parse_card(text: str) -> CardBlock | None:
    """从文本中提取第一个 card 块，返回 CardBlock 或 None。"""
    match = _CARD_PATTERN.search(text)
    if not match:
        return None

    card_type = match.group(1)
    json_str = match.group(2).strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("卡片 JSON 解析失败 (type=%s): %s", card_type, e)
        return None

    return CardBlock(card_type=card_type, data=data)


def make_card_reminder(tool_call_id: str) -> str:
    """生成追加到 tool result 末尾的 system-reminder 提示。"""
    return CARD_REMINDER_TEMPLATE.format(tool_call_id=tool_call_id)

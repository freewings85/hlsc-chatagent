"""话痨说车业务请求上下文。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo

logger: logging.Logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.business_map_hook import BusinessMapPreprocessor


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行，确保 LLM 始终能看到当前车辆、位置、业务地图切片和状态树。
    """

    def __init__(self, preprocessor: BusinessMapPreprocessor | None = None) -> None:
        self._preprocessor: BusinessMapPreprocessor | None = preprocessor

    def format(self, context: RequestContext) -> str:
        # 支持 dict（从 HTTP 请求直接传入）和 HlscRequestContext
        if isinstance(context, dict):
            try:
                context = HlscRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, HlscRequestContext):
            return ""

        parts: list[str] = []

        if context.current_car is not None:
            car: CarInfo = context.current_car
            parts.append(
                f"current_car(car_model_id={car.car_model_id}, "
                f"car_model_name={car.car_model_name}, "
                f"vin_code={car.vin_code})"
            )
        else:
            parts.append("current_car: (未设置)")

        if context.current_location is not None:
            loc: LocationInfo = context.current_location
            parts.append(
                f"current_location(address={loc.address}, "
                f"lat={loc.lat}, lng={loc.lng})"
            )
        else:
            parts.append("current_location: (未设置)")

        result: str = "[request_context]: " + ", ".join(parts)

        # 注入业务地图切片和状态树（来自 BusinessMapPreprocessor）
        # 使用说明仅在有切片时才注入，避免无切片时的 token 浪费和注意力稀释
        if self._preprocessor is not None:
            sid: str = self._preprocessor.current_session_id
            slice_md: str | None = self._preprocessor.get_slice(sid)
            state_tree: str | None = self._preprocessor.get_state_tree(sid)

            logger.info(
                "formatter 注入: session=%s, has_slice=%s, has_state_tree=%s, slice_len=%d",
                sid, bool(slice_md), bool(state_tree),
                len(slice_md) if slice_md else 0,
            )

            if slice_md or state_tree:
                result += "\n\n" + _BUSINESS_MAP_INSTRUCTIONS

            if slice_md:
                result += f"\n\n[business_map_slice]:\n{slice_md}"

            if state_tree:
                result += f"\n\n[state_tree]:\n{state_tree}"
                # 动态提醒：状态树已存在时，提醒 LLM 在有业务进展时更新
                result += (
                    "\n\n[reminder]: 如果本轮用户确认了选择、改变了意图、"
                    "或完成了步骤信息收集，请先调用 update_state_tree 更新进度再回复。"
                )
            elif slice_md:
                result += "\n\n[state_tree]: (尚未创建，请在本轮回复结束前调用 update_state_tree 创建)"
        else:
            logger.warning("formatter: preprocessor 为 None，跳过切片注入")

        logger.info("formatter 输出长度: %d", len(result))
        return result


# 业务地图使用说明（仅在有切片/状态树时注入，不污染无业务场景的 prompt）
_BUSINESS_MAP_INSTRUCTIONS: str = """[business_map_instructions]:
切片解读：每个 ### 段落是一个业务节点，按层级从浅到深排列。多路径用 --- 分隔。
状态标记：[完成] → 产出 / [进行中] ← 当前 / [跳过] / [ ] 未开始

使用原则：
- 切片是主要参考，优先按 checklist 推进；但如果用户意图明显偏离切片内容，以用户为准
- 需要更多节点详情时调用 read_business_node
- 闲聊或无业务进展时不需要更新状态树

update_state_tree 调用规则（重要 — 不调用会导致进度丢失）：
- 如果 [state_tree] 不存在 → 本轮必须调用 update_state_tree 创建初始状态树
- 如果 [state_tree] 已存在，以下场景必须在回复用户之前先调用 update_state_tree：
  · 用户确认了选择（如确认项目、选定方案、选择优惠方式）
  · 用户改变了意图或切换到其他业务分支
  · 当前步骤的信息收集已完成，准备进入下一步
- 调用时传入完整的更新后状态树，用标记反映最新进度""".strip()

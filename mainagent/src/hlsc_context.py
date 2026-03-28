"""话痨说车业务请求上下文。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo

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

            if slice_md or state_tree:
                result += "\n\n" + _BUSINESS_MAP_INSTRUCTIONS

            if slice_md:
                result += f"\n\n[business_map_slice]:\n{slice_md}"

            if state_tree:
                result += f"\n\n[state_tree]:\n{state_tree}"

        return result


# 业务地图使用说明（仅在有切片/状态树时注入，不污染无业务场景的 prompt）
_BUSINESS_MAP_INSTRUCTIONS: str = """[business_map_instructions]:
切片解读：每个 ### 段落是一个业务节点，按层级从浅到深排列。多路径用 --- 分隔。
状态标记：[完成] → 产出 / [进行中] ← 当前 / [跳过] / [ ] 未开始

使用原则：
- 切片是主要参考，优先按 checklist 推进；但如果用户意图明显偏离切片内容，以用户为准
- 用户确认、完成步骤、做出选择后，先调用 update_state_tree 保存进度，再回复用户
- 需要更多节点详情时调用 read_business_node
- 闲聊或无业务进展时不需要更新状态树""".strip()

"""MainAgent 工具：更新会话槽位状态。

MainAgent 的 LLM 调用此工具来增量更新 SlotState，
将变更持久化到 session 目录下的 slot_state.json 文件。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.slot_state_service import SlotState, slot_state_service


def _get_session_dir(deps: AgentDeps) -> Path:
    """获取当前 session 的存储目录。"""
    inner_dir: str = os.getenv("INNER_STORAGE_DIR", "data/inner")
    return Path(inner_dir) / deps.user_id / "sessions" / deps.session_id


async def update_slots(
    ctx: RunContext[AgentDeps],
    updates: Annotated[str, Field(
        description='JSON 格式的槽位更新，如 {"project_name": "小保养", "vehicle_info": null}'
    )],
) -> str:
    """更新当前会话的槽位状态。当用户确认了选择、改变了意图、或完成了信息收集时调用。

    参数 updates 是 JSON 字符串，key 为槽位名，value 为新值（null 表示清除该槽位）。

    示例：
    - 确认项目：{"project_id": "502", "project_name": "小保养（换机油+机滤）"}
    - 改变意图：{"project_id": null, "project_name": null}
    - 确认商户：{"merchant": "途虎养车张江店"}
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_slots", sid, rid, {"updates": updates})

    # 1. 构建 session 目录
    session_dir: Path = _get_session_dir(ctx.deps)

    # 2. 读取现有 SlotState（不存在则创建空状态）
    state: SlotState = slot_state_service.read(session_dir) or SlotState()

    # 3. 解析 updates JSON
    try:
        parsed: dict[str, Any] = json.loads(updates)
    except json.JSONDecodeError as e:
        error_msg: str = f"updates 参数不是合法 JSON: {e}"
        log_tool_end("update_slots", sid, rid, {"error": error_msg})
        return error_msg

    if not isinstance(parsed, dict):
        error_msg = "updates 参数必须是 JSON 对象（dict），不能是数组或基本类型"
        log_tool_end("update_slots", sid, rid, {"error": error_msg})
        return error_msg

    # 4. 遍历更新槽位
    updated_keys: list[str] = []
    name: str
    value: Any
    for name, value in parsed.items():
        # value 必须是 str 或 None
        if value is not None and not isinstance(value, str):
            value = str(value)
        state.set_slot(name, value)
        updated_keys.append(name)

    # 5. 写回持久化
    slot_state_service.write(session_dir, state)

    # 6. 返回确认消息
    filled: dict[str, str] = state.get_filled_slots()
    result_msg: str = f"已更新 {len(updated_keys)} 个槽位: {', '.join(updated_keys)}。当前有值槽位: {filled}"
    log_tool_end("update_slots", sid, rid, {"updated": updated_keys, "filled": filled})
    return result_msg

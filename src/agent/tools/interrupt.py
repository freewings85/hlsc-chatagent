"""interrupt 工具：向前端发送结构化卡片事件，然后正常结束本轮请求。

设计思路（参照 cjml-cheap-weixiu 的 LangGraph interrupt → 会话制模型迁移）：
- LangGraph 中 interrupt() 暂停图执行，需要 resume 机制恢复
- chatagent 中改为 SSE 事件：发出 INTERRUPT 卡片事件后正常结束
- 用户对卡片的操作（确认/修改/取消）成为下一条消息，LLM 自然处理

前端收到 interrupt 事件后根据 type 渲染对应卡片组件。
"""

import json

from pydantic_ai import RunContext

from src.agent.deps import AgentDeps
from src.event.event_model import EventModel
from src.event.event_type import EventType


async def interrupt(
    ctx: RunContext[AgentDeps],
    type: str,
    data: str,
) -> str:
    """向前端发送一个结构化交互卡片（如确认表单、报价列表等）。

    发送后本轮 tool 调用正常返回，用户在前端操作卡片后的反馈
    会作为下一条消息进入对话。

    Args:
        type: 卡片类型标识（如 "inquiry_confirm", "inquiry_result"）。
        data: JSON 字符串，卡片需要的数据。

    Returns:
        确认消息，告知 LLM 卡片已发送。
    """
    emitter = ctx.deps.emitter
    if emitter is None:
        return "[interrupt unavailable: no event emitter]"

    # 解析 data JSON
    try:
        parsed_data = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        parsed_data = {"raw": data}

    await emitter.emit(EventModel(
        conversation_id=ctx.deps.session_id,
        request_id="",
        type=EventType.INTERRUPT,
        data={
            "type": type,
            **parsed_data,
        },
    ))

    return f"已向用户展示 {type} 卡片，等待用户在下一轮消息中反馈。不要猜测用户的选择，等待用户回复。"

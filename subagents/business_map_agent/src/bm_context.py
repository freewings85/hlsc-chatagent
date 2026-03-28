"""BusinessMapAgent 请求上下文。"""

from __future__ import annotations

from pydantic import Field

from agent_sdk._common.request_context import ContextFormatter, RequestContext


class BusinessMapRequestContext(RequestContext):
    """业务地图定位器请求上下文（由 app.py 通过 A2A context 传入）"""

    state_briefing: str = Field(default="", description="状态简报（从 state_tree.md 压缩）")
    recent_history: str = Field(default="", description="最近几轮对话摘要")


class BusinessMapContextFormatter(ContextFormatter):
    """将 BusinessMapRequestContext 格式化为注入 LLM 的文本。"""

    def format(self, context: RequestContext) -> str:
        if isinstance(context, dict):
            try:
                context = BusinessMapRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, BusinessMapRequestContext):
            return ""

        parts: list[str] = []
        if context.state_briefing:
            parts.append(f"[状态简报]\n{context.state_briefing}")
        if context.recent_history:
            parts.append(f"[最近对话]\n{context.recent_history}")

        if not parts:
            return "[request_context]: (无额外上下文)"

        return "[request_context]:\n" + "\n\n".join(parts)

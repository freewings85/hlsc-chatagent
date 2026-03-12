"""MemoryContextService：请求上下文工作集管理接口。

管理用户请求中附带的额外上下文（如位置、车辆信息等）。
调用方对比新旧 context，只在有变化时注入消息。

核心操作：
- get()           — 获取最新上下文
- set()           — 更新上下文
- diff()          — 对比并返回变化的字段
- format_changed() — 将变化格式化为注入文本（可通过 formatter 参数自定义）
"""

from __future__ import annotations

import abc
import json
from typing import Any, Callable

from src.common.request_context import RequestContext

# 格式化函数签名：接收变化字段 dict，返回注入文本
ContextFormatter = Callable[[dict[str, Any]], str]


def _default_formatter(changed: dict[str, Any]) -> str:
    """默认格式化：JSON dump。"""
    return "用户请求上下文（已更新的字段）：\n" + json.dumps(changed, ensure_ascii=False)


class MemoryContextService(abc.ABC):
    """请求上下文工作集管理接口。

    构造时可传入 formatter 自定义变化字段的格式化逻辑，
    不传则使用默认 JSON dump。
    """

    def __init__(self, formatter: ContextFormatter | None = None) -> None:
        self._formatter: ContextFormatter = formatter or _default_formatter

    @abc.abstractmethod
    async def get(self, user_id: str, session_id: str) -> RequestContext | None:
        """获取指定 session 的最新上下文。"""

    @abc.abstractmethod
    async def set(
        self,
        user_id: str,
        session_id: str,
        context: RequestContext,
    ) -> None:
        """更新指定 session 的上下文。"""

    async def diff(
        self,
        user_id: str,
        session_id: str,
        new_context: RequestContext,
    ) -> dict[str, Any] | None:
        """对比新旧上下文，返回变化的字段（dict 形式）。无变化返回 None。

        默认实现：将 RequestContext 序列化为 dict 后逐字段对比。
        """
        new_data = new_context.model_dump(exclude_none=True)
        if not new_data:
            return None
        old = await self.get(user_id, session_id)
        old_data = old.model_dump(exclude_none=True) if old else {}
        changed: dict[str, Any] = {}
        for key, value in new_data.items():
            if old_data.get(key) != value:
                changed[key] = value
        return changed if changed else None

    def format_changed(self, changed: dict[str, Any]) -> str:
        """将变化的字段格式化为注入消息的文本。"""
        return self._formatter(changed)

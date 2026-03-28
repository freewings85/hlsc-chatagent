"""BusinessMapAgent 预处理钩子：每次用户请求时自动触发业务地图导航。

流程：
1. 读取 session 下的 state_tree.md
2. 调用 BusinessMapAgent subagent (A2A) 获取节点 ID
3. 使用 BusinessMapService 组装切片
4. 将切片和状态树存入共享状态，供 ContextFormatter 注入 LLM
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
from pathlib import Path
from typing import Any

from hlsc.services.business_map_service import business_map_service
from hlsc.services.state_tree_service import state_tree_service

# 使用 contextvars 实现 async-safe 的 session 隔离。
# 每个 asyncio Task 拥有独立的 session_id，不会跨请求泄漏。
_current_session_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bm_current_session", default="default"
)

logger: logging.Logger = logging.getLogger(__name__)

BUSINESS_MAP_AGENT_URL: str = os.getenv(
    "BUSINESS_MAP_AGENT_URL", "http://localhost:8103"
)

# 业务地图 YAML 目录
BUSINESS_MAP_DIR: str = os.getenv(
    "BUSINESS_MAP_DIR",
    str(Path(__file__).resolve().parents[1] / "business-map"),
)


_MAX_CACHED_SESSIONS: int = 100
"""最大缓存 session 数量，超过后清理最早的条目。"""

# 意图跳转关键词：信号粗粒度，用于判断是否需要重新导航
_INTENT_KEYWORDS: list[str] = [
    "找店", "附近", "推荐", "商户",      # merchant_search
    "预订", "预约", "下单", "约",         # booking
    "保养", "换", "修", "轮胎",          # project_saving
    "省钱", "便宜", "优惠", "比价",      # confirm_saving
    "算了", "不做了", "改成", "换个",    # 意图改变
]


class BusinessMapPreprocessor:
    """业务地图预处理器：管理 hook 和 formatter 之间的共享状态。

    hook 在 agent.run() 前执行，将导航结果写入 session 级别的共享状态。
    HlscContextFormatter 在每次 LLM 调用时读取该状态并注入 prompt。
    """

    def __init__(self) -> None:
        self._loaded: bool = False
        # session_id → 最新切片和状态树（有上限，防止内存泄漏）
        self._slices: dict[str, str] = {}
        self._state_trees: dict[str, str] = {}
        self._nav_state_trees: dict[str, str | None] = {}  # 上次导航时的状态树快照

    def ensure_loaded(self) -> None:
        """确保 BusinessMapService 已加载。"""
        if not self._loaded:
            try:
                business_map_service.load(BUSINESS_MAP_DIR)
                self._loaded = True
                logger.info("BusinessMapService 已加载: %s", BUSINESS_MAP_DIR)
            except Exception:
                logger.error("BusinessMapService 加载失败: %s", BUSINESS_MAP_DIR, exc_info=True)

    @property
    def current_session_id(self) -> str:
        """当前 async task 的 session_id（从 contextvars 读取，async-safe）。"""
        return _current_session_var.get()

    def get_slice(self, session_id: str) -> str | None:
        """获取指定 session 的最新切片（供 formatter 使用）。"""
        return self._slices.get(session_id)

    def get_state_tree(self, session_id: str) -> str | None:
        """获取指定 session 的最新状态树（供 formatter 使用）。"""
        return self._state_trees.get(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """清理指定 session 的缓存状态。"""
        self._slices.pop(session_id, None)
        self._state_trees.pop(session_id, None)
        self._nav_state_trees.pop(session_id, None)

    def _evict_if_needed(self) -> None:
        """当缓存超过上限时，清理最早的条目。"""
        while len(self._slices) > _MAX_CACHED_SESSIONS:
            oldest_key: str = next(iter(self._slices))
            self._slices.pop(oldest_key, None)
            self._state_trees.pop(oldest_key, None)
            self._nav_state_trees.pop(oldest_key, None)

    def _should_navigate(
        self,
        session_id: str,
        message: str,
        current_state_tree: str | None,
    ) -> bool:
        """混合策略判断是否需要调用 navigator。

        R1: 无缓存 → 必须调用
        R2: 状态树变了 → 必须调用
        R3: 短消息且无意图关键词 → 跳过
        R4: 包含意图跳转关键词 → 调用
        R5: 其他长消息 → 调用（宁可多调，不漏意图）
        """
        # R1: 无缓存 → 必须调用
        if session_id not in self._slices:
            return True

        # R2: 状态树变了 → 必须调用
        if current_state_tree != self._nav_state_trees.get(session_id):
            return True

        # R3: 短消息且无意图关键词 → 跳过
        stripped: str = message.strip()
        if len(stripped) <= 8 and not any(kw in stripped for kw in _INTENT_KEYWORDS):
            return False

        # R4: 包含意图跳转关键词 → 调用
        if any(kw in stripped for kw in _INTENT_KEYWORDS):
            return True

        # R5: 其他长消息 → 调用（宁可多调，不漏意图）
        return True

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: Any,
        message: str,
    ) -> None:
        """BeforeAgentRunHook 实现：预处理业务地图导航。"""
        # 使用 contextvars 设置当前 session_id，确保 async-safe（不跨请求泄漏）
        _current_session_var.set(session_id)

        self.ensure_loaded()
        if not self._loaded:
            return

        self._evict_if_needed()

        inner_dir: str = os.getenv("INNER_STORAGE_DIR", "data/inner")
        session_dir: Path = Path(inner_dir) / user_id / "sessions" / session_id

        # 1. 读取当前状态树
        state_tree: str | None = state_tree_service.read(session_dir)
        if state_tree:
            self._state_trees[session_id] = state_tree

        # 2. 混合策略判断是否需要调用 navigator
        should_nav: bool = self._should_navigate(session_id, message, state_tree)

        if not should_nav:
            logger.debug("复用缓存切片: session=%s, msg=%s", session_id, message[:20])
            return

        # 3. 调用 BusinessMapAgent (A2A) 获取节点 ID
        node_ids: list[str] = await self._call_navigator(
            message=message,
            state_tree=state_tree,
            deps=deps,
        )

        if not node_ids:
            logger.info("BusinessMapAgent 未返回节点 ID，跳过切片组装")
            return

        # 4. 组装切片
        try:
            slice_md: str = business_map_service.assemble_slice(node_ids)
            if slice_md:
                self._slices[session_id] = slice_md
                self._nav_state_trees[session_id] = state_tree
                logger.info(
                    "业务地图切片已组装: session=%s, node_ids=%s, 长度=%d",
                    session_id, node_ids, len(slice_md),
                )
        except Exception:
            logger.error("切片组装失败", exc_info=True)

    async def _call_navigator(
        self,
        message: str,
        state_tree: str | None,
        deps: Any,
    ) -> list[str]:
        """调用 BusinessMapAgent subagent (A2A) 获取节点 ID。

        当 subagent 不可用或调用失败时，返回空列表（graceful degradation）。
        此时 MainAgent 本轮不会收到业务地图切片，但不影响其他功能。
        """
        try:
            from agent_sdk.a2a.call_subagent import call_subagent

            # 构造简报
            briefing: str = ""
            if state_tree:
                briefing = _compress_state_tree(state_tree)

            context: dict[str, str] = {
                "state_briefing": briefing,
                "recent_history": message,
            }

            result: str = await asyncio.wait_for(
                call_subagent(
                    deps, url=BUSINESS_MAP_AGENT_URL, message=message, context=context
                ),
                timeout=5.0,
            )

            # 解析逗号分隔的 ID
            return _parse_node_ids(result)

        except asyncio.TimeoutError:
            logger.warning("BusinessMapAgent A2A 调用超时（5s），跳过导航")
            return []
        except Exception:
            logger.warning(
                "BusinessMapAgent 调用失败，跳过导航", exc_info=True
            )
            return []


def _compress_state_tree(state_tree: str) -> str:
    """将状态树压缩为自然语言简报。

    规则：
    - "已完成" 列出所有 [完成] 节点的标题和产出
    - "当前在做" 用 → 串联从最近顶层到 ← 当前 的路径
    - 不包含 [ ]（未开始）的节点
    """
    completed: list[str] = []
    current_path: list[str] = []
    has_current: bool = False

    line: str
    for line in state_tree.splitlines():
        stripped: str = line.strip()
        if not stripped.startswith("- "):
            continue

        content: str = stripped[2:].strip()

        if content.startswith("[完成]"):
            text: str = content[4:].strip()
            completed.append(text)
        elif content.startswith("[跳过]"):
            text = content[4:].strip()
            completed.append(f"{text}（已跳过）")
        elif "← 当前" in content:
            has_current = True
            text = content.replace("← 当前", "").strip()
            if text.startswith("[进行中]"):
                text = text[5:].strip()
            current_path.append(text)
        elif content.startswith("[进行中]"):
            text = content[5:].strip()
            current_path.append(text)

    parts: list[str] = []
    if completed:
        parts.append("已完成：")
        item: str
        for item in completed:
            parts.append(f"- {item}")
    if current_path:
        parts.append(f"当前在做：{'→'.join(current_path)}")

    return "\n".join(parts) if parts else ""


def _parse_node_ids(raw: str) -> list[str]:
    """解析逗号分隔的节点 ID 字符串。"""
    if not raw or not raw.strip():
        return []
    ids: list[str] = []
    part: str
    for part in raw.split(","):
        cleaned: str = part.strip()
        if cleaned:
            ids.append(cleaned)
    return ids


# 模块级单例
business_map_preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()

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
import re
from pathlib import Path
from typing import Any

from hlsc.business_map.model import BusinessNode
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
    str(Path(__file__).resolve().parents[2] / "extensions" / "business-map" / "data"),
)


_MAX_CACHED_SESSIONS: int = 100
"""最大缓存 session 数量，超过后清理最早的条目。"""

# 意图跳转关键词：信号粗粒度，用于判断是否需要重新导航
def _load_intent_keywords() -> list[str]:
    """从 intent_keywords.yaml 加载意图关键词列表。"""
    import yaml
    keywords_file: Path = (
        Path(__file__).resolve().parents[2] / "extensions" / "business-map" / "intent_keywords.yaml"
    )
    if not keywords_file.exists():
        logger.warning("意图关键词文件不存在: %s，使用空列表", keywords_file)
        return []
    with open(keywords_file, "r", encoding="utf-8") as f:
        data: dict[str, list[str]] = yaml.safe_load(f)
    keywords: list[str] = []
    group: list[str]
    for group in data.values():
        if isinstance(group, list):
            keywords.extend(group)
    return keywords


_INTENT_KEYWORDS: list[str] = _load_intent_keywords()


class _NullEmitter:
    """空操作 emitter：实现 EventEmitter 接口但不发送任何事件。

    用于 _SilentDeps，让 SubagentSession 正常收集 _text_parts，
    同时不将 BMA 的中间输出泄漏到用户前端。
    """

    async def emit(self, event: Any) -> None:
        """静默丢弃所有事件。"""
        pass

    async def close(self) -> None:
        """空操作。"""
        pass


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

        # R3: 包含意图跳转关键词 → 无论长度都调用
        stripped: str = message.strip()
        if any(kw in stripped for kw in _INTENT_KEYWORDS):
            return True

        # R4: 短消息且无关键词 → 跳过
        if len(stripped) <= 8:
            return False

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

            # call_subagent 期望 ctx.deps 形式，构造一个简单包装。
            #
            # 关键设计：使用 _NullEmitter 替代 emitter=None。
            #
            # 为什么不能用 emitter=None：
            #   SubagentSession._emit_artifacts() 在 emitter is None 时会 early-return，
            #   导致 TextPart artifact 中的文本不会被收集到 _text_parts，
            #   最终 session.result 可能丢失 BMA 的输出。
            #
            # 为什么不能用原始 emitter：
            #   BMA 的中间输出（工具调用 JSON、节点 ID 原文）会通过 TEXT 事件
            #   泄漏到用户聊天界面。
            #
            # _NullEmitter 的作用：
            #   实现 EventEmitter 接口但 emit() 是空操作，既不泄漏到前端，
            #   又让 SubagentSession 正常走完全部逻辑（包括 _text_parts 收集）。
            silent_emitter: _NullEmitter = _NullEmitter()

            class _SilentDeps:
                """包装 deps，用 _NullEmitter 替换真实 emitter。"""
                def __init__(self, real_deps: Any, emitter: _NullEmitter) -> None:
                    self._real: Any = real_deps
                    self.emitter: _NullEmitter = emitter

                def __getattr__(self, name: str) -> Any:
                    return getattr(self._real, name)

            class _CtxShim:
                def __init__(self, deps: Any) -> None:
                    self.deps: Any = deps

            ctx_shim: _CtxShim = _CtxShim(_SilentDeps(deps, silent_emitter))

            result: str = await asyncio.wait_for(
                call_subagent(
                    ctx_shim, url=BUSINESS_MAP_AGENT_URL, message=message, context=context
                ),
                timeout=30.0,
            )

            logger.info("BMA 原始返回: %s", repr(result[:300]) if result else "(empty)")
            # 解析逗号分隔的 ID
            return _parse_node_ids(result)

        except asyncio.TimeoutError:
            logger.warning("BusinessMapAgent A2A 调用超时（30s），跳过导航")
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


# 正则解析时过滤的噪声词：JSON 常见 key、布尔值等
_PARSE_NOISE: frozenset[str] = frozenset({
    "node_id", "node_ids", "text", "kind", "role", "type",
    "name", "root", "true", "false", "null", "none",
    "parts", "data", "result", "status", "state", "message",
    "completed", "failed", "working", "content", "agent",
    "the", "node", "relevant", "output", "response",
})

# 匹配 JSON 对象的正则（贪婪匹配一对花括号）
_JSON_BLOCK_RE: re.Pattern[str] = re.compile(r"\{[^{}]*\}")

# 匹配 markdown 代码块
_CODE_BLOCK_RE: re.Pattern[str] = re.compile(r"```[\s\S]*?```")


def _clean_raw_output(raw: str) -> str:
    """清洗 BMA 原始返回，去除 JSON 块和 markdown 代码块等干扰。

    保留纯文本中的节点 ID，便于正则提取。
    """
    # 去掉 markdown 代码块（```...```）
    cleaned: str = _CODE_BLOCK_RE.sub(" ", raw)
    # 去掉 JSON 对象（{...}）
    cleaned = _JSON_BLOCK_RE.sub(" ", cleaned)
    # 去掉 markdown 反引号
    cleaned = cleaned.replace("`", " ")
    return cleaned


def _parse_node_ids(raw: str) -> list[str]:
    """从原始返回中提取有效的节点 ID。

    解析策略（按优先级）：
    1. 先清洗 raw：去除 markdown 反引号、JSON 块等干扰内容
    2. 用正则提取合法的 snake_case 标识符
    3. 验证 ID 是否存在于业务地图中，过滤掉 LLM 幻觉 ID
    4. 兜底：若无有效 ID，尝试将中文节点名称映射回 ID
    """
    if not raw or not raw.strip():
        return []
    logger.info("_parse_node_ids raw: %s", repr(raw[:300]))

    # 第一步：清洗——去掉 JSON 块和 markdown 代码块，减少干扰
    cleaned: str = _clean_raw_output(raw)

    # 第二步：用正则提取 snake_case 标识符（节点 ID 格式）
    # 匹配规则：以字母开头，由字母/数字/下划线组成，至少 3 字符
    all_matches: list[str] = re.findall(r"\b([a-z][a-z0-9_]{2,})\b", cleaned)
    # 过滤掉常见的非 ID 噪声词
    ids: list[str] = [m for m in all_matches if m not in _PARSE_NOISE]

    # 去重（保持顺序）
    seen: set[str] = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]

    # 第三步：验证 ID 是否真实存在于业务地图中，过滤掉 LLM 幻觉
    valid_ids: list[str] = _validate_node_ids(ids)
    if valid_ids:
        if len(valid_ids) < len(ids):
            logger.warning(
                "_parse_node_ids: 过滤掉不存在的 ID: %s",
                [i for i in ids if i not in valid_ids],
            )
        return valid_ids

    # 兜底：LLM 可能输出了中文名称而非英文 ID，尝试 name → id 映射
    name_map: dict[str, str] = _get_name_to_id_map()
    if name_map:
        fallback_ids: list[str] = []
        node_name: str
        node_id: str
        for node_name, node_id in name_map.items():
            if node_name in raw:
                fallback_ids.append(node_id)
        if fallback_ids:
            logger.info("_parse_node_ids 兜底：中文名称映射到 ID: %s", fallback_ids)
            return fallback_ids

    return []


def _validate_node_ids(ids: list[str]) -> list[str]:
    """验证节点 ID 是否存在于业务地图中，过滤掉 LLM 幻觉的 ID。"""
    if not business_map_service.is_loaded or not ids:
        return ids  # 未加载时无法验证，原样返回
    known_ids: set[str] = business_map_service._biz_map.all_ids()
    return [i for i in ids if i in known_ids]


def _get_name_to_id_map() -> dict[str, str]:
    """从已加载的 BusinessMapService 构建 name → id 映射。

    按名称长度倒序排列，避免短名称抢先匹配长名称的子串。
    """
    if not business_map_service.is_loaded:
        return {}
    try:
        all_ids: set[str] = business_map_service._biz_map.all_ids()
        name_map: dict[str, str] = {}
        node_id: str
        for node_id in all_ids:
            node: BusinessNode = business_map_service.find(node_id)
            name_map[node.name] = node_id
        # 按名称长度倒序，优先匹配长名称（避免"需求沟通"匹配到"需求"子串）
        sorted_map: dict[str, str] = dict(
            sorted(name_map.items(), key=lambda x: len(x[0]), reverse=True)
        )
        return sorted_map
    except Exception:
        logger.warning("构建 name→id 映射失败", exc_info=True)
        return {}


# 模块级单例
business_map_preprocessor: BusinessMapPreprocessor = BusinessMapPreprocessor()

"""决策树求值引擎：根据因子值走决策树，返回命中的场景 ID。

条件表达式语法：
  intent.xxx                 → bool 因子为 true
  NOT intent.xxx             → bool 因子为 false
  intent.xxx == "值"         → enum 因子等于某值
  条件1 AND 条件2            → 同时满足
  条件1 OR 条件2             → 满足其一
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from hlsc.services.scene_service import TreeNode

logger: logging.Logger = logging.getLogger(__name__)

# 因子值类型：bool / str / None
FactorValues = dict[str, Any]


@dataclass
class TreeEvalResult:
    """决策树求值结果。"""

    scene_id: str
    path: list[str] = field(default_factory=list)


# ============================================================
# 条件表达式求值
# ============================================================

# 匹配 intent.xxx == "值"
_EQ_PATTERN: re.Pattern[str] = re.compile(r'(\S+)\s*==\s*"([^"]*)"')


def _eval_single(expr: str, factors: FactorValues) -> bool:
    """求值单个原子条件。"""
    expr = expr.strip()

    # NOT
    if expr.startswith("NOT "):
        inner: str = expr[4:].strip()
        return not _eval_single(inner, factors)

    # == 比较
    match: re.Match[str] | None = _EQ_PATTERN.match(expr)
    if match:
        factor_name: str = match.group(1)
        expected: str = match.group(2)
        return factors.get(factor_name) == expected

    # bool 因子
    val: Any = factors.get(expr)
    return bool(val)


def _eval_condition(condition: str, factors: FactorValues) -> bool:
    """求值条件表达式（支持 AND / OR，不支持嵌套括号）。

    优先级：OR 拆分 → 每个子句内 AND 拆分 → 原子求值。
    """
    # OR 拆分
    or_parts: list[str] = condition.split(" OR ")
    or_part: str
    for or_part in or_parts:
        # AND 拆分
        and_parts: list[str] = or_part.split(" AND ")
        all_true: bool = all(_eval_single(p, factors) for p in and_parts)
        if all_true:
            return True
    return False


# ============================================================
# 决策树求值
# ============================================================


def evaluate_tree(tree: list[TreeNode], factors: FactorValues) -> TreeEvalResult:
    """从根开始走决策树，返回命中的场景 ID 和路径。"""
    path: list[str] = []

    def _walk(nodes: list[TreeNode]) -> str | None:
        node: TreeNode
        for node in nodes:
            # 兜底节点（无条件）
            if node.condition is None:
                if node.scene:
                    path.append(f"fallback→{node.scene}")
                    return node.scene
                continue

            # 条件求值
            if _eval_condition(node.condition, factors):
                path.append(node.condition)
                # 条件 → 场景
                if node.scene:
                    path.append(f"→{node.scene}")
                    return node.scene
                # 条件 → 子树
                if node.children:
                    result: str | None = _walk(node.children)
                    if result:
                        return result
        return None

    scene_id: str | None = _walk(tree)
    if scene_id is None:
        logger.warning("决策树未命中任何场景，使用默认兜底")
        scene_id = "EXPLORE_MODE"

    return TreeEvalResult(scene_id=scene_id, path=path)

"""决策树求值引擎：条件表达式解析、因子求值、决策树遍历。

条件表达式语法（递归下降解析）：
    expr       := or_expr
    or_expr    := and_expr ("OR" and_expr)*
    and_expr   := not_expr ("AND" not_expr)*
    not_expr   := "NOT" atom | atom
    atom       := factor_ref | factor_ref "==" quoted_value
    factor_ref := "slot." IDENT | "intent." IDENT
    quoted_value := '"' ... '"' | "'" ... "'"

优先级：NOT > AND > OR
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TypeAlias

from hlsc.services.scene_service import KeywordFactor, TreeNode


# ============================================================
# 条件表达式 AST 节点
# ============================================================


@dataclass
class ConditionNode:
    """条件表达式 AST 节点基类。"""

    pass


@dataclass
class FactorRef(ConditionNode):
    """因子引用节点。

    判断因子是否存在（非 None）。
    例如 ``slot.project_id``。
    """

    name: str  # e.g. "slot.project_id"


@dataclass
class Comparison(ConditionNode):
    """比较节点。

    判断因子值是否等于指定字符串。
    例如 ``intent.project_category == "轮胎"``。
    """

    factor: str  # e.g. "intent.project_category"
    value: str   # e.g. "轮胎"


@dataclass
class NotExpr(ConditionNode):
    """逻辑非节点。"""

    operand: ConditionNode


@dataclass
class AndExpr(ConditionNode):
    """逻辑与节点。"""

    operands: list[ConditionNode] = field(default_factory=list)


@dataclass
class OrExpr(ConditionNode):
    """逻辑或节点。"""

    operands: list[ConditionNode] = field(default_factory=list)


# ============================================================
# 因子值类型
# ============================================================

FactorValues: TypeAlias = dict[str, str | bool | None]
"""因子值字典。

示例：
    "slot.project_id" -> None | "502"
    "intent.has_car_service" -> True | False
    "intent.project_category" -> "轮胎" | None
"""


# ============================================================
# 词法分析器（Tokenizer）
# ============================================================

# 令牌正则：关键字 / 标识符（含点号）/ 字符串字面量 / 运算符
_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r"""
    \s*                          # 跳过前导空白
    (?:
        (AND|OR|NOT)(?!\w)       # 组1：逻辑关键字（后面不能跟单词字符，避免匹配 ANDROID 等）
      | (==)                     # 组2：比较运算符
      | "([^"]*)"               # 组3：双引号字符串内容
      | '([^']*)'               # 组4：单引号字符串内容
      | ([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)  # 组5：标识符（slot.xxx / intent.xxx）
    )
    """,
    re.VERBOSE,
)


@dataclass
class _Token:
    """词法令牌。"""

    kind: str   # "KEYWORD" | "EQ" | "STRING" | "IDENT"
    value: str


def _tokenize(expr: str) -> list[_Token]:
    """将条件表达式字符串拆分为令牌列表。"""
    tokens: list[_Token] = []
    pos: int = 0
    while pos < len(expr):
        # 跳过空白
        match: re.Match[str] | None = _TOKEN_PATTERN.match(expr, pos)
        if match is None:
            # 跳过单个空白字符
            if expr[pos].isspace():
                pos += 1
                continue
            raise ValueError(
                f"条件表达式解析错误：位置 {pos} 处无法识别的字符 '{expr[pos]}'"
            )
        if match.group(1):  # 逻辑关键字
            tokens.append(_Token(kind="KEYWORD", value=match.group(1)))
        elif match.group(2):  # ==
            tokens.append(_Token(kind="EQ", value="=="))
        elif match.group(3) is not None:  # 双引号字符串
            tokens.append(_Token(kind="STRING", value=match.group(3)))
        elif match.group(4) is not None:  # 单引号字符串
            tokens.append(_Token(kind="STRING", value=match.group(4)))
        elif match.group(5):  # 标识符
            tokens.append(_Token(kind="IDENT", value=match.group(5)))
        pos = match.end()
    return tokens


# ============================================================
# 递归下降解析器
# ============================================================


class _Parser:
    """递归下降条件表达式解析器。

    语法规则：
        expr       := or_expr
        or_expr    := and_expr ("OR" and_expr)*
        and_expr   := not_expr ("AND" not_expr)*
        not_expr   := "NOT" atom | atom
        atom       := factor_ref ("==" quoted_value)?
        factor_ref := IDENT（形如 slot.xxx 或 intent.xxx）
    """

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens: list[_Token] = tokens
        self._pos: int = 0

    def _peek(self) -> _Token | None:
        """查看当前令牌，不前进。"""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self) -> _Token:
        """消费当前令牌，返回之。"""
        token: _Token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect_kind(self, kind: str) -> _Token:
        """断言当前令牌类型并消费。"""
        token: _Token | None = self._peek()
        if token is None or token.kind != kind:
            expected: str = kind
            got: str = f"{token.kind}({token.value})" if token else "EOF"
            raise ValueError(f"条件表达式解析错误：期望 {expected}，实际 {got}")
        return self._advance()

    def parse(self) -> ConditionNode:
        """解析入口，返回 AST 根节点。"""
        node: ConditionNode = self._parse_or_expr()
        if self._pos < len(self._tokens):
            leftover: _Token = self._tokens[self._pos]
            raise ValueError(
                f"条件表达式解析错误：多余的令牌 {leftover.kind}({leftover.value})"
            )
        return node

    def _parse_or_expr(self) -> ConditionNode:
        """or_expr := and_expr ("OR" and_expr)*"""
        left: ConditionNode = self._parse_and_expr()
        operands: list[ConditionNode] = [left]
        while self._peek() is not None and self._peek_is_keyword("OR"):
            self._advance()  # 消费 OR
            right: ConditionNode = self._parse_and_expr()
            operands.append(right)
        if len(operands) == 1:
            return operands[0]
        return OrExpr(operands=operands)

    def _parse_and_expr(self) -> ConditionNode:
        """and_expr := not_expr ("AND" not_expr)*"""
        left: ConditionNode = self._parse_not_expr()
        operands: list[ConditionNode] = [left]
        while self._peek() is not None and self._peek_is_keyword("AND"):
            self._advance()  # 消费 AND
            right: ConditionNode = self._parse_not_expr()
            operands.append(right)
        if len(operands) == 1:
            return operands[0]
        return AndExpr(operands=operands)

    def _parse_not_expr(self) -> ConditionNode:
        """not_expr := "NOT" atom | atom"""
        if self._peek() is not None and self._peek_is_keyword("NOT"):
            self._advance()  # 消费 NOT
            inner: ConditionNode = self._parse_atom()
            return NotExpr(operand=inner)
        return self._parse_atom()

    def _parse_atom(self) -> ConditionNode:
        """atom := factor_ref ("==" quoted_value)?"""
        ident_token: _Token = self._expect_kind("IDENT")
        factor_name: str = ident_token.value

        # 检查是否有 == 比较
        if self._peek() is not None and self._peek().kind == "EQ":  # type: ignore[union-attr]
            self._advance()  # 消费 ==
            string_token: _Token = self._expect_kind("STRING")
            return Comparison(factor=factor_name, value=string_token.value)

        return FactorRef(name=factor_name)

    def _peek_is_keyword(self, keyword: str) -> bool:
        """检查当前令牌是否为指定关键字。"""
        token: _Token | None = self._peek()
        return token is not None and token.kind == "KEYWORD" and token.value == keyword


# ============================================================
# 解析缓存
# ============================================================

_condition_cache: dict[str, ConditionNode] = {}


def parse_condition(expr: str) -> ConditionNode:
    """解析条件表达式字符串为 AST。

    结果会缓存，重复调用直接返回。
    """
    if expr in _condition_cache:
        return _condition_cache[expr]
    tokens: list[_Token] = _tokenize(expr)
    parser: _Parser = _Parser(tokens)
    node: ConditionNode = parser.parse()
    _condition_cache[expr] = node
    return node


def _do_parse(expr: str) -> ConditionNode:
    """不带缓存的解析（内部使用，parse_condition 的底层实现）。"""
    tokens: list[_Token] = _tokenize(expr)
    parser: _Parser = _Parser(tokens)
    return parser.parse()


# ============================================================
# 条件求值
# ============================================================


def evaluate_condition(node: ConditionNode, factors: FactorValues) -> bool | None:
    """求值条件表达式。返回 None 表示因子缺失无法判断。

    求值规则：
    - FactorRef: 因子存在且不为 None 时为 True
    - Comparison: 因子值等于指定字符串时为 True
    - NotExpr: 反转（None 仍为 None）
    - AndExpr: 全 True 才 True，有 False 就 False，有 None 且无 False 就 None
    - OrExpr: 有 True 就 True，全 False 才 False，有 None 就 None
    """
    if isinstance(node, FactorRef):
        return _evaluate_factor_ref(node, factors)
    if isinstance(node, Comparison):
        return _evaluate_comparison(node, factors)
    if isinstance(node, NotExpr):
        return _evaluate_not(node, factors)
    if isinstance(node, AndExpr):
        return _evaluate_and(node, factors)
    if isinstance(node, OrExpr):
        return _evaluate_or(node, factors)
    raise TypeError(f"未知的条件节点类型: {type(node).__name__}")


def _evaluate_factor_ref(node: FactorRef, factors: FactorValues) -> bool | None:
    """FactorRef 求值：因子在字典中且值不为 None 时为 True。

    slot.* 因子是确定性的：值为 None 表示"没有值"→ False，不是"不可判断"。
    intent.* 因子不在字典中时返回 None（需要 LLM 判断，尚未获取）。
    """
    if node.name not in factors:
        # slot 因子不在字典中也视为确定的 False（不应出现，但防御性处理）
        if node.name.startswith("slot."):
            return False
        return None
    value: str | bool | None = factors[node.name]
    if value is None:
        # slot 因子值为 None = 没有值 = False（确定性）
        if node.name.startswith("slot."):
            return False
        return None
    if isinstance(value, bool):
        return value
    # 字符串值：非空为 True
    return True


def _evaluate_comparison(node: Comparison, factors: FactorValues) -> bool | None:
    """Comparison 求值：因子值等于指定字符串。

    slot.* 因子缺失或为 None 时返回 False（确定性：没有值不可能等于任何字符串）。
    intent.* 因子缺失或为 None 时返回 None（需要 LLM 判断）。
    """
    if node.factor not in factors:
        if node.factor.startswith("slot."):
            return False
        return None
    value: str | bool | None = factors[node.factor]
    if value is None:
        if node.factor.startswith("slot."):
            return False
        return None
    return value == node.value


def _evaluate_not(node: NotExpr, factors: FactorValues) -> bool | None:
    """NotExpr 求值：反转内部结果，None 不变。"""
    inner_result: bool | None = evaluate_condition(node.operand, factors)
    if inner_result is None:
        return None
    return not inner_result


def _evaluate_and(node: AndExpr, factors: FactorValues) -> bool | None:
    """AndExpr 求值：全 True 才 True，有 False 就 False，有 None 且无 False 就 None。"""
    has_none: bool = False
    operand: ConditionNode
    for operand in node.operands:
        result: bool | None = evaluate_condition(operand, factors)
        if result is False:
            return False
        if result is None:
            has_none = True
    if has_none:
        return None
    return True


def _evaluate_or(node: OrExpr, factors: FactorValues) -> bool | None:
    """OrExpr 求值：有 True 就 True，全 False 才 False，有 None 就 None。"""
    has_none: bool = False
    operand: ConditionNode
    for operand in node.operands:
        result: bool | None = evaluate_condition(operand, factors)
        if result is True:
            return True
        if result is None:
            has_none = True
    if has_none:
        return None
    return False


# ============================================================
# 关键词因子求值
# ============================================================


def evaluate_keyword_factors(
    message: str,
    keyword_factors: list[KeywordFactor],
) -> dict[str, bool]:
    """对用户消息做关键词匹配，返回因子值。

    遍历每个 KeywordFactor，只要消息中包含任一关键词就为 True，否则 False。
    """
    result: dict[str, bool] = {}
    factor: KeywordFactor
    for factor in keyword_factors:
        matched: bool = False
        keyword: str
        for keyword in factor.keywords:
            if keyword in message:
                matched = True
                break
        result[factor.name] = matched
    return result


# ============================================================
# 决策树求值
# ============================================================


@dataclass
class TreeEvalResult:
    """决策树求值结果。"""

    scene_id: str
    path: list[str]  # 经过的节点 label（调试用）


def collect_bma_factors_needed(
    tree: list[TreeNode],
    known_factors: FactorValues,
) -> list[str]:
    """收集决策树当前路径上还需要的 BMA 因子名称。

    边走边收集：遇到已知因子就判断走哪个分支，
    遇到未知的 intent.* 因子就加入需求列表。
    """
    needed: list[str] = []
    _seen_names: set[str] = set()

    def _collect_from_nodes(nodes: list[TreeNode]) -> None:
        """递归收集因子需求。"""
        node: TreeNode
        for node in nodes:
            if node.condition is None:
                # 兜底节点，不需要因子
                continue

            # 解析条件，提取引用的因子名
            ast: ConditionNode = parse_condition(node.condition)
            factor_names: list[str] = _extract_factor_names(ast)

            # 检查是否有未知的 intent.* 因子
            name: str
            for name in factor_names:
                if name.startswith("intent.") and name not in known_factors:
                    if name not in _seen_names:
                        needed.append(name)
                        _seen_names.add(name)

            # 尝试求值当前条件
            result: bool | None = evaluate_condition(ast, known_factors)

            if result is True:
                # 条件命中，如果有子树则继续收集子树中的因子
                if node.children is not None:
                    _collect_from_nodes(node.children)
                # 命中后停止同级后续节点
                return
            elif result is False:
                # 条件不满足，继续同级下一个节点
                continue
            else:
                # result is None：因子缺失，无法判断
                # 继续看同级后续节点（可能有其他路径也需要因子）
                continue

    _collect_from_nodes(tree)
    return needed


def _extract_factor_names(node: ConditionNode) -> list[str]:
    """从 AST 中提取所有引用的因子名称。"""
    names: list[str] = []
    if isinstance(node, FactorRef):
        names.append(node.name)
    elif isinstance(node, Comparison):
        names.append(node.factor)
    elif isinstance(node, NotExpr):
        names.extend(_extract_factor_names(node.operand))
    elif isinstance(node, AndExpr):
        operand: ConditionNode
        for operand in node.operands:
            names.extend(_extract_factor_names(operand))
    elif isinstance(node, OrExpr):
        operand2: ConditionNode
        for operand2 in node.operands:
            names.extend(_extract_factor_names(operand2))
    return names


def evaluate_tree(
    tree: list[TreeNode],
    factors: FactorValues,
) -> TreeEvalResult:
    """遍历决策树，返回命中的场景 ID。

    从上到下匹配，第一个命中的 if 进入子树或返回 scene。
    无条件节点作为兜底。

    Raises:
        ValueError: 决策树无法命中任何场景（配置缺少兜底节点）。
    """
    path: list[str] = []

    def _walk(nodes: list[TreeNode]) -> str | None:
        """递归遍历节点列表，返回命中的 scene_id 或 None。"""
        node: TreeNode
        for node in nodes:
            if node.condition is None:
                # 兜底节点（无条件），直接命中
                if node.label is not None:
                    path.append(node.label)
                if node.scene is not None:
                    return node.scene
                # 兜底节点有子树（理论上不常见，但支持）
                if node.children is not None:
                    result: str | None = _walk(node.children)
                    if result is not None:
                        return result
                continue

            # 有条件的节点
            ast: ConditionNode = parse_condition(node.condition)
            eval_result: bool | None = evaluate_condition(ast, factors)

            if eval_result is True:
                if node.label is not None:
                    path.append(node.label)
                if node.scene is not None:
                    return node.scene
                if node.children is not None:
                    child_result: str | None = _walk(node.children)
                    if child_result is not None:
                        return child_result
                # 条件命中但没有 scene 也没有 children 命中，停止同级
                return None
            # eval_result is False 或 None：继续同级下一个
            continue

        return None

    scene_id: str | None = _walk(tree)
    if scene_id is None:
        raise ValueError("决策树无法命中任何场景，请检查配置是否缺少兜底节点")
    return TreeEvalResult(scene_id=scene_id, path=path)

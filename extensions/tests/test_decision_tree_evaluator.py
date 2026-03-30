"""决策树求值引擎测试。

覆盖：
- 条件表达式解析器（各种语法）
- 条件求值（三值逻辑）
- 关键词因子匹配
- collect_bma_factors_needed
- evaluate_tree
"""

from __future__ import annotations

import pytest

from hlsc.services.decision_tree_evaluator import (
    AndExpr,
    Comparison,
    ConditionNode,
    FactorRef,
    FactorValues,
    NotExpr,
    OrExpr,
    TreeEvalResult,
    _condition_cache,
    _do_parse,
    collect_bma_factors_needed,
    evaluate_condition,
    evaluate_keyword_factors,
    evaluate_tree,
    parse_condition,
)
from hlsc.services.scene_service import KeywordFactor, TreeNode


# ============================================================
# 条件解析器测试
# ============================================================


class TestParseCondition:
    """条件表达式解析测试。"""

    def test_simple_slot_factor(self) -> None:
        """简单 slot 条件：slot.project_id"""
        node: ConditionNode = _do_parse("slot.project_id")
        assert isinstance(node, FactorRef)
        assert node.name == "slot.project_id"

    def test_simple_intent_factor(self) -> None:
        """简单 intent 条件：intent.has_car_service"""
        node: ConditionNode = _do_parse("intent.has_car_service")
        assert isinstance(node, FactorRef)
        assert node.name == "intent.has_car_service"

    def test_not_condition(self) -> None:
        """NOT 条件：NOT slot.project_id"""
        node: ConditionNode = _do_parse("NOT slot.project_id")
        assert isinstance(node, NotExpr)
        assert isinstance(node.operand, FactorRef)
        assert node.operand.name == "slot.project_id"

    def test_and_condition(self) -> None:
        """AND 组合：slot.project_id AND slot.saving_plan_type"""
        node: ConditionNode = _do_parse("slot.project_id AND slot.saving_plan_type")
        assert isinstance(node, AndExpr)
        assert len(node.operands) == 2
        assert isinstance(node.operands[0], FactorRef)
        assert node.operands[0].name == "slot.project_id"
        assert isinstance(node.operands[1], FactorRef)
        assert node.operands[1].name == "slot.saving_plan_type"

    def test_or_condition(self) -> None:
        """OR 组合：slot.project_id OR intent.has_car_service"""
        node: ConditionNode = _do_parse("slot.project_id OR intent.has_car_service")
        assert isinstance(node, OrExpr)
        assert len(node.operands) == 2
        assert isinstance(node.operands[0], FactorRef)
        assert isinstance(node.operands[1], FactorRef)

    def test_comparison_double_quote(self) -> None:
        """比较条件（双引号）：intent.project_category == "轮胎" """
        node: ConditionNode = _do_parse('intent.project_category == "轮胎"')
        assert isinstance(node, Comparison)
        assert node.factor == "intent.project_category"
        assert node.value == "轮胎"

    def test_comparison_single_quote(self) -> None:
        """比较条件（单引号）：intent.project_category == '保险' """
        node: ConditionNode = _do_parse("intent.project_category == '保险'")
        assert isinstance(node, Comparison)
        assert node.factor == "intent.project_category"
        assert node.value == "保险"

    def test_mixed_not_and(self) -> None:
        """混合条件：NOT slot.project_id AND intent.has_car_service"""
        node: ConditionNode = _do_parse(
            "NOT slot.project_id AND intent.has_car_service"
        )
        assert isinstance(node, AndExpr)
        assert len(node.operands) == 2
        # 第一个操作数是 NOT
        assert isinstance(node.operands[0], NotExpr)
        assert isinstance(node.operands[0].operand, FactorRef)
        assert node.operands[0].operand.name == "slot.project_id"
        # 第二个操作数是普通因子
        assert isinstance(node.operands[1], FactorRef)
        assert node.operands[1].name == "intent.has_car_service"

    def test_precedence_not_higher_than_and(self) -> None:
        """优先级：NOT > AND — NOT a AND b 解析为 (NOT a) AND b"""
        node: ConditionNode = _do_parse("NOT slot.a AND slot.b")
        assert isinstance(node, AndExpr)
        assert isinstance(node.operands[0], NotExpr)
        assert isinstance(node.operands[1], FactorRef)

    def test_precedence_and_higher_than_or(self) -> None:
        """优先级：AND > OR — a OR b AND c 解析为 a OR (b AND c)"""
        node: ConditionNode = _do_parse("slot.a OR slot.b AND slot.c")
        assert isinstance(node, OrExpr)
        assert len(node.operands) == 2
        assert isinstance(node.operands[0], FactorRef)
        assert isinstance(node.operands[1], AndExpr)

    def test_three_way_and(self) -> None:
        """三个 AND 操作数。"""
        node: ConditionNode = _do_parse("slot.a AND slot.b AND slot.c")
        assert isinstance(node, AndExpr)
        assert len(node.operands) == 3

    def test_three_way_or(self) -> None:
        """三个 OR 操作数。"""
        node: ConditionNode = _do_parse("slot.a OR slot.b OR slot.c")
        assert isinstance(node, OrExpr)
        assert len(node.operands) == 3

    def test_parse_error_expect_kind_eof(self) -> None:
        """_expect_kind 遇到 EOF 时抛 ValueError。"""
        # "NOT" 后面没有 IDENT → 期望 IDENT，实际 EOF
        with pytest.raises(ValueError, match="期望"):
            _do_parse("NOT")

    def test_parse_error_expect_kind_wrong_token(self) -> None:
        """_expect_kind 遇到错误令牌类型时抛 ValueError。"""
        # "NOT ==" → NOT 后面期望 IDENT，实际是 EQ
        with pytest.raises(ValueError, match="期望"):
            _do_parse("NOT ==")

    def test_parse_error_invalid_char(self) -> None:
        """无效字符抛 ValueError。"""
        with pytest.raises(ValueError, match="无法识别"):
            _do_parse("slot.a & slot.b")

    def test_parse_error_extra_tokens(self) -> None:
        """多余令牌抛 ValueError。"""
        with pytest.raises(ValueError, match="多余的令牌"):
            _do_parse("slot.a slot.b")

    def test_parse_condition_cache(self) -> None:
        """parse_condition 使用缓存。"""
        # 清除缓存中可能已有的条目
        expr: str = "slot.cache_test_unique_key"
        _condition_cache.pop(expr, None)

        node1: ConditionNode = parse_condition(expr)
        node2: ConditionNode = parse_condition(expr)
        assert node1 is node2  # 同一个对象（缓存命中）

        # 清理
        _condition_cache.pop(expr, None)


# ============================================================
# 条件求值测试（三值逻辑）
# ============================================================


class TestEvaluateCondition:
    """条件求值三值逻辑测试。"""

    # -- FactorRef --

    def test_factor_ref_true_string(self) -> None:
        """FactorRef：字符串值存在 → True"""
        factors: FactorValues = {"slot.project_id": "502"}
        result: bool | None = evaluate_condition(FactorRef(name="slot.project_id"), factors)
        assert result is True

    def test_factor_ref_true_bool(self) -> None:
        """FactorRef：布尔 True → True"""
        factors: FactorValues = {"intent.has_car_service": True}
        result: bool | None = evaluate_condition(
            FactorRef(name="intent.has_car_service"), factors
        )
        assert result is True

    def test_factor_ref_false_bool(self) -> None:
        """FactorRef：布尔 False → False"""
        factors: FactorValues = {"intent.has_car_service": False}
        result: bool | None = evaluate_condition(
            FactorRef(name="intent.has_car_service"), factors
        )
        assert result is False

    def test_factor_ref_slot_none_value(self) -> None:
        """FactorRef：slot 因子值为 None → False（确定性：没有值）"""
        factors: FactorValues = {"slot.project_id": None}
        result: bool | None = evaluate_condition(FactorRef(name="slot.project_id"), factors)
        assert result is False

    def test_factor_ref_slot_missing(self) -> None:
        """FactorRef：slot 因子不存在 → False（确定性：没有值）"""
        factors: FactorValues = {}
        result: bool | None = evaluate_condition(FactorRef(name="slot.project_id"), factors)
        assert result is False

    def test_factor_ref_intent_none_value(self) -> None:
        """FactorRef：intent 因子值为 None → None（需要 LLM 判断）"""
        factors: FactorValues = {"intent.has_car_service": None}
        result: bool | None = evaluate_condition(
            FactorRef(name="intent.has_car_service"), factors
        )
        assert result is None

    def test_factor_ref_intent_missing(self) -> None:
        """FactorRef：intent 因子不存在 → None（需要 LLM 判断）"""
        factors: FactorValues = {}
        result: bool | None = evaluate_condition(
            FactorRef(name="intent.has_car_service"), factors
        )
        assert result is None

    # -- Comparison --

    def test_comparison_equal(self) -> None:
        """Comparison：值匹配 → True"""
        factors: FactorValues = {"intent.project_category": "轮胎"}
        result: bool | None = evaluate_condition(
            Comparison(factor="intent.project_category", value="轮胎"), factors
        )
        assert result is True

    def test_comparison_not_equal(self) -> None:
        """Comparison：值不匹配 → False"""
        factors: FactorValues = {"intent.project_category": "保险"}
        result: bool | None = evaluate_condition(
            Comparison(factor="intent.project_category", value="轮胎"), factors
        )
        assert result is False

    def test_comparison_missing(self) -> None:
        """Comparison：因子缺失 → None"""
        factors: FactorValues = {}
        result: bool | None = evaluate_condition(
            Comparison(factor="intent.project_category", value="轮胎"), factors
        )
        assert result is None

    def test_comparison_none_value(self) -> None:
        """Comparison：因子值为 None → None"""
        factors: FactorValues = {"intent.project_category": None}
        result: bool | None = evaluate_condition(
            Comparison(factor="intent.project_category", value="轮胎"), factors
        )
        assert result is None

    # -- NotExpr --

    def test_not_true(self) -> None:
        """NOT True → False"""
        factors: FactorValues = {"slot.a": "val"}
        result: bool | None = evaluate_condition(
            NotExpr(operand=FactorRef(name="slot.a")), factors
        )
        assert result is False

    def test_not_false(self) -> None:
        """NOT False → True"""
        factors: FactorValues = {"slot.a": False}
        result: bool | None = evaluate_condition(
            NotExpr(operand=FactorRef(name="slot.a")), factors
        )
        assert result is True

    def test_not_slot_none(self) -> None:
        """NOT slot(None) → NOT False → True（slot 因子确定性）"""
        factors: FactorValues = {}
        result: bool | None = evaluate_condition(
            NotExpr(operand=FactorRef(name="slot.a")), factors
        )
        assert result is True

    def test_not_intent_none(self) -> None:
        """NOT intent(None) → None（intent 因子不可判断）"""
        factors: FactorValues = {}
        result: bool | None = evaluate_condition(
            NotExpr(operand=FactorRef(name="intent.x")), factors
        )
        assert result is None

    # -- AndExpr --

    def test_and_true_true(self) -> None:
        """True AND True → True"""
        factors: FactorValues = {"slot.a": "1", "slot.b": "2"}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is True

    def test_and_true_false(self) -> None:
        """True AND False → False"""
        factors: FactorValues = {"slot.a": "1", "slot.b": False}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is False

    def test_and_false_none(self) -> None:
        """False AND None → False（短路：有 False 即 False）"""
        factors: FactorValues = {"slot.a": False}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is False

    def test_and_true_none(self) -> None:
        """True AND None → None（使用 intent 因子触发 None）"""
        factors: FactorValues = {"slot.a": "1"}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="intent.x")]
        )
        assert evaluate_condition(node, factors) is None

    def test_and_none_none(self) -> None:
        """None AND None → None（使用 intent 因子触发 None）"""
        factors: FactorValues = {}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="intent.x"), FactorRef(name="intent.y")]
        )
        assert evaluate_condition(node, factors) is None

    def test_and_slot_missing_is_false(self) -> None:
        """slot.a(有值) AND slot.b(缺失) → True AND False → False"""
        factors: FactorValues = {"slot.a": "1"}
        node: AndExpr = AndExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is False

    # -- OrExpr --

    def test_or_true_false(self) -> None:
        """True OR False → True"""
        factors: FactorValues = {"slot.a": "1", "slot.b": False}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is True

    def test_or_false_false(self) -> None:
        """False OR False → False"""
        factors: FactorValues = {"slot.a": False, "slot.b": False}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is False

    def test_or_true_none(self) -> None:
        """True OR None → True（短路：有 True 即 True）"""
        factors: FactorValues = {"slot.a": "1"}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is True

    def test_or_false_none(self) -> None:
        """False OR None → None（使用 intent 因子触发 None）"""
        factors: FactorValues = {"slot.a": False}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="intent.x")]
        )
        assert evaluate_condition(node, factors) is None

    def test_or_none_none(self) -> None:
        """None OR None → None（使用 intent 因子触发 None）"""
        factors: FactorValues = {}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="intent.x"), FactorRef(name="intent.y")]
        )
        assert evaluate_condition(node, factors) is None

    def test_or_slot_missing_is_false(self) -> None:
        """slot.a(False) OR slot.b(缺失) → False OR False → False"""
        factors: FactorValues = {"slot.a": False}
        node: OrExpr = OrExpr(
            operands=[FactorRef(name="slot.a"), FactorRef(name="slot.b")]
        )
        assert evaluate_condition(node, factors) is False

    # -- 未知节点类型 --

    def test_unknown_node_type(self) -> None:
        """未知节点类型抛 TypeError。"""

        class FakeNode(ConditionNode):
            pass

        with pytest.raises(TypeError, match="未知的条件节点类型"):
            evaluate_condition(FakeNode(), {})


# ============================================================
# 关键词因子匹配测试
# ============================================================


class TestEvaluateKeywordFactors:
    """关键词因子匹配测试。"""

    def test_keyword_hit(self) -> None:
        """消息中包含关键词 → True"""
        kw_factors: list[KeywordFactor] = [
            KeywordFactor(name="intent.has_urgent", keywords=["抛锚", "事故"]),
        ]
        result: dict[str, bool] = evaluate_keyword_factors("我车抛锚了", kw_factors)
        assert result["intent.has_urgent"] is True

    def test_keyword_miss(self) -> None:
        """消息中不包含关键词 → False"""
        kw_factors: list[KeywordFactor] = [
            KeywordFactor(name="intent.has_urgent", keywords=["抛锚", "事故"]),
        ]
        result: dict[str, bool] = evaluate_keyword_factors("我想做保养", kw_factors)
        assert result["intent.has_urgent"] is False

    def test_keyword_empty_message(self) -> None:
        """空消息 → False"""
        kw_factors: list[KeywordFactor] = [
            KeywordFactor(name="intent.has_urgent", keywords=["抛锚"]),
        ]
        result: dict[str, bool] = evaluate_keyword_factors("", kw_factors)
        assert result["intent.has_urgent"] is False

    def test_multiple_factors(self) -> None:
        """多个因子同时匹配。"""
        kw_factors: list[KeywordFactor] = [
            KeywordFactor(name="intent.has_urgent", keywords=["抛锚", "事故"]),
            KeywordFactor(name="intent.has_intent_change", keywords=["算了", "不做了"]),
        ]
        result: dict[str, bool] = evaluate_keyword_factors("出事故了算了", kw_factors)
        assert result["intent.has_urgent"] is True
        assert result["intent.has_intent_change"] is True

    def test_no_factors(self) -> None:
        """空因子列表 → 空结果。"""
        result: dict[str, bool] = evaluate_keyword_factors("随便什么消息", [])
        assert result == {}


# ============================================================
# collect_bma_factors_needed 测试
# ============================================================


class TestCollectBmaFactorsNeeded:
    """收集 BMA 因子需求测试。"""

    def test_slot_factors_sufficient(self) -> None:
        """slot 因子够用时返回空列表。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.project_id", scene="DIRECT"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {"slot.project_id": "502"}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert needed == []

    def test_needs_intent_factor(self) -> None:
        """需要 intent 因子时返回列表。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_car_service", scene="CAR_SERVICE"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert "intent.has_car_service" in needed

    def test_nested_children_factor_collection(self) -> None:
        """嵌套子树中的因子收集。"""
        tree: list[TreeNode] = [
            TreeNode(
                condition="slot.project_id",
                children=[
                    TreeNode(
                        condition="intent.expression_clarity == \"specific\"",
                        scene="DIRECT",
                    ),
                    TreeNode(condition=None, scene="FALLBACK"),
                ],
            ),
            TreeNode(condition=None, scene="GLOBAL_FALLBACK"),
        ]
        # slot.project_id 有值 → 命中，进入子树收集
        factors: FactorValues = {"slot.project_id": "502"}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert "intent.expression_clarity" in needed

    def test_known_intent_factor_not_needed(self) -> None:
        """已知的 intent 因子不再需要。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_car_service", scene="CAR_SERVICE"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {"intent.has_car_service": True}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert needed == []

    def test_slot_factor_not_collected_as_bma(self) -> None:
        """slot 因子缺失不会被收集为 BMA 需求。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.project_id", scene="DIRECT"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert needed == []  # slot.* 不以 intent. 开头

    def test_dedup_factors(self) -> None:
        """同名因子去重。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_car_service", scene="A"),
            TreeNode(condition="intent.has_car_service", scene="B"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert needed.count("intent.has_car_service") == 1

    def test_fallback_node_no_condition(self) -> None:
        """兜底节点（无 condition）不产生因子需求。"""
        tree: list[TreeNode] = [
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert needed == []

    def test_collect_skips_false_condition(self) -> None:
        """条件为 False 时跳过，继续同级节点收集。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.a", scene="A"),
            TreeNode(condition="intent.b", scene="B"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        # intent.a 已知为 False → 跳过，intent.b 未知 → 收集
        factors: FactorValues = {"intent.a": False}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert "intent.b" in needed
        assert "intent.a" not in needed

    def test_collect_from_or_expr(self) -> None:
        """OR 表达式中的 intent 因子也能被收集。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.x OR intent.y", scene="COMBINED"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}
        needed: list[str] = collect_bma_factors_needed(tree, factors)
        assert "intent.x" in needed
        assert "intent.y" in needed


# ============================================================
# evaluate_tree 测试
# ============================================================


class TestEvaluateTree:
    """决策树求值测试。"""

    def test_simple_condition_hit(self) -> None:
        """简单条件命中直接返回场景。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.project_id", scene="DIRECT", label="直接"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {"slot.project_id": "502"}
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "DIRECT"
        assert "直接" in result.path

    def test_nested_children(self) -> None:
        """嵌套子树：条件命中后进入 children。"""
        tree: list[TreeNode] = [
            TreeNode(
                condition="slot.project_id AND slot.saving_plan_type",
                label="S2 阶段",
                children=[
                    TreeNode(condition="NOT slot.merchant", scene="FIND_MERCHANT"),
                    TreeNode(condition="NOT slot.booking_time", scene="CONFIRM_BOOKING"),
                    TreeNode(condition=None, scene="COMPLETED"),
                ],
            ),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        # S2 阶段：项目和方案都有，但商户没选
        # 修复后：slot 因子值为 None → False（确定性），NOT False → True
        factors: FactorValues = {
            "slot.project_id": "502",
            "slot.saving_plan_type": "coupon",
            "slot.merchant": None,
            "slot.booking_time": None,
        }
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "FIND_MERCHANT"
        assert "S2 阶段" in result.path

    def test_fallback_node(self) -> None:
        """所有条件不满足走兜底。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.project_id", scene="DIRECT"),
            TreeNode(condition=None, scene="CASUAL_CHAT", label="兜底"),
        ]
        factors: FactorValues = {"slot.project_id": None}
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "CASUAL_CHAT"
        assert "兜底" in result.path

    def test_no_match_raises(self) -> None:
        """所有节点都不命中且无兜底 → ValueError。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.project_id", scene="DIRECT"),
        ]
        factors: FactorValues = {"slot.project_id": None}
        with pytest.raises(ValueError, match="无法命中任何场景"):
            evaluate_tree(tree, factors)

    def test_condition_false_skips_to_next(self) -> None:
        """条件为 False 时跳到下一个同级节点。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_urgent", scene="URGENT"),
            TreeNode(condition="slot.project_id", scene="DIRECT"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {
            "intent.has_urgent": False,
            "slot.project_id": "502",
        }
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "DIRECT"

    def test_condition_none_skips_to_next(self) -> None:
        """条件为 None（缺失）时跳到下一个同级节点。"""
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_car_service", scene="CAR"),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {}  # intent 因子缺失
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "FALLBACK"

    def test_nested_fallback_in_children(self) -> None:
        """子树中的兜底节点。"""
        tree: list[TreeNode] = [
            TreeNode(
                condition="slot.project_id",
                label="有项目",
                children=[
                    TreeNode(condition="slot.merchant", scene="HAS_MERCHANT"),
                    TreeNode(condition=None, scene="NO_MERCHANT"),
                ],
            ),
            TreeNode(condition=None, scene="GLOBAL_FALLBACK"),
        ]
        factors: FactorValues = {
            "slot.project_id": "502",
            "slot.merchant": None,
        }
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "NO_MERCHANT"

    def test_comparison_condition_in_tree(self) -> None:
        """决策树中使用比较条件。"""
        tree: list[TreeNode] = [
            TreeNode(
                condition='intent.project_category == "保险"',
                scene="INSURANCE",
            ),
            TreeNode(
                condition='intent.project_category == "轮胎"',
                scene="TIRE",
            ),
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {"intent.project_category": "轮胎"}
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "TIRE"

    def test_fallback_with_children(self) -> None:
        """兜底节点有子树（无条件 + children）。"""
        tree: list[TreeNode] = [
            TreeNode(
                condition=None,
                label="兜底带子树",
                children=[
                    TreeNode(condition="slot.a", scene="A"),
                    TreeNode(condition=None, scene="INNER_FALLBACK"),
                ],
            ),
        ]
        factors: FactorValues = {"slot.a": False}
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "INNER_FALLBACK"
        assert "兜底带子树" in result.path

    def test_condition_hit_no_scene_no_children(self) -> None:
        """条件命中但既无 scene 也无 children → 返回 None，走兜底。"""
        tree: list[TreeNode] = [
            TreeNode(condition="slot.a", label="空命中"),  # 无 scene 和 children
            TreeNode(condition=None, scene="FALLBACK"),
        ]
        factors: FactorValues = {"slot.a": "val"}
        # 条件命中但没有 scene，停止同级 → _walk 返回 None → ValueError
        with pytest.raises(ValueError, match="无法命中任何场景"):
            evaluate_tree(tree, factors)

    def test_complex_tree_s1_flow(self) -> None:
        """模拟完整 S1 流程：未确认项目 + 有养车意图 + 直接表达。

        修复后：slot 因子值为 None → False（确定性），NOT slot.project_id → True。
        """
        tree: list[TreeNode] = [
            TreeNode(condition="intent.has_urgent", scene="URGENT"),
            TreeNode(
                condition="slot.project_id AND slot.saving_plan_type",
                label="S2",
                children=[
                    TreeNode(condition=None, scene="COMPLETED"),
                ],
            ),
            TreeNode(
                condition="NOT slot.project_id AND intent.has_car_service",
                label="有养车意图",
                children=[
                    TreeNode(
                        condition='intent.expression_clarity == "specific"',
                        scene="DIRECT_PROJECT",
                    ),
                    TreeNode(condition=None, scene="FUZZY_PROJECT"),
                ],
            ),
            TreeNode(condition=None, scene="CASUAL_CHAT"),
        ]
        # slot.project_id = None → False（确定性），NOT False → True
        factors: FactorValues = {
            "intent.has_urgent": False,
            "slot.project_id": None,
            "slot.saving_plan_type": None,
            "intent.has_car_service": True,
            "intent.expression_clarity": "specific",
        }
        result: TreeEvalResult = evaluate_tree(tree, factors)
        assert result.scene_id == "DIRECT_PROJECT"
        assert "有养车意图" in result.path

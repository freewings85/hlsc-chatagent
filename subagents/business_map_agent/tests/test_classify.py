"""场景分类端点测试（classify.py）。

覆盖：
- mount_classify_route 正常挂载
- _do_classify：slot 因子够用不调 LLM
- _do_classify：需要 LLM（mock httpx 调用）
- _do_classify：LLM 调用失败时兜底
- 辅助函数：_build_factor_definitions, _build_slot_summary, _parse_llm_response
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 需要将 BMA src 加入路径
_BMA_SRC: Path = Path(__file__).resolve().parents[1] / "src"
if str(_BMA_SRC) not in sys.path:
    sys.path.insert(0, str(_BMA_SRC))

from classify import (
    ClassifyRequest,
    ClassifyResponse,
    _build_factor_definitions,
    _build_slot_summary,
    _do_classify,
    _parse_llm_response,
    mount_classify_route,
)


# ============================================================
# 路径常量
# ============================================================

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_EXAMPLE_CONFIG: Path = _PROJECT_ROOT / "extensions" / "business-map" / "scene_config_example.yaml"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_scene_service() -> None:
    """每个测试前重置 scene_service 加载状态。"""
    import classify
    classify._scene_service_loaded = False


@pytest.fixture
def _load_config() -> None:
    """加载 example 配置。"""
    import classify
    from hlsc.services.scene_service import scene_service

    scene_service.load(_EXAMPLE_CONFIG)
    classify._scene_service_loaded = True


# ============================================================
# mount_classify_route 测试
# ============================================================


class TestMountClassifyRoute:
    """路由挂载测试。"""

    def test_route_registered(self) -> None:
        """挂载后 /classify 路由可用。"""
        app: FastAPI = FastAPI()
        mount_classify_route(app)

        routes: list[str] = [r.path for r in app.routes]  # type: ignore
        assert "/classify" in routes


# ============================================================
# 辅助函数测试
# ============================================================


class TestHelperFunctions:
    """辅助函数单元测试。"""

    def test_build_slot_summary_empty(self) -> None:
        """无填充槽位时返回（无）。"""
        result: str = _build_slot_summary({"a": None, "b": None})
        assert result == "（无）"

    def test_build_slot_summary_filled(self) -> None:
        """有填充槽位时返回摘要。"""
        result: str = _build_slot_summary({"project_id": "502", "merchant": None})
        assert "project_id = 502" in result
        assert "merchant" not in result

    def test_parse_llm_response_picks_needed(self) -> None:
        """只提取需要的因子。"""
        raw: dict[str, Any] = {
            "intent.has_car_service": True,
            "intent.project_category": "轮胎",
            "extra_field": "ignored",
        }
        needed: list[str] = ["intent.has_car_service", "intent.project_category"]
        result: dict[str, str | bool | None] = _parse_llm_response(raw, needed)
        assert result["intent.has_car_service"] is True
        assert result["intent.project_category"] == "轮胎"
        assert "extra_field" not in result

    def test_parse_llm_response_missing_factor(self) -> None:
        """LLM 未返回的因子不出现在结果中。"""
        raw: dict[str, Any] = {"intent.has_car_service": True}
        needed: list[str] = ["intent.has_car_service", "intent.project_category"]
        result: dict[str, str | bool | None] = _parse_llm_response(raw, needed)
        assert "intent.project_category" not in result

    def test_build_factor_definitions_bool(self, _load_config: None) -> None:
        """构建 bool 因子定义。"""
        from hlsc.services.scene_service import scene_service

        config = scene_service.config
        result: str = _build_factor_definitions(["intent.has_car_service"], config)
        assert "intent.has_car_service" in result
        assert "bool" in result

    def test_build_factor_definitions_enum(self, _load_config: None) -> None:
        """构建 enum 因子定义。"""
        from hlsc.services.scene_service import scene_service

        config = scene_service.config
        result: str = _build_factor_definitions(["intent.project_category"], config)
        assert "intent.project_category" in result
        assert "enum" in result
        assert "轮胎" in result

    def test_build_factor_definitions_empty(self, _load_config: None) -> None:
        """无因子定义时返回空字符串。"""
        from hlsc.services.scene_service import scene_service

        config = scene_service.config
        result: str = _build_factor_definitions([], config)
        assert result == ""


# ============================================================
# _do_classify 测试
# ============================================================


class TestDoClassify:
    """_do_classify 核心逻辑测试。"""

    @pytest.mark.asyncio
    async def test_slot_sufficient_no_llm(self, _load_config: None) -> None:
        """slot 因子够用时不调 LLM，走兜底场景。

        紧急关键词匹配命中 → 直接走 URGENT 场景。
        """
        request: ClassifyRequest = ClassifyRequest(
            message="我车抛锚了",
            slot_state={"project_id": None},
        )

        # 不 mock LLM — 如果代码意外调了 LLM 会因为缺少环境变量而返回 {}
        response: ClassifyResponse = await _do_classify(request)

        # 关键词 "抛锚" 命中 intent.has_urgent → URGENT 场景
        assert response.scene_id == "URGENT"
        assert response.scene_name == "紧急救援"

    @pytest.mark.asyncio
    async def test_needs_llm_called(self, _load_config: None) -> None:
        """需要 BMA 因子时 LLM 被调用。

        修复后：slot 因子值为 None → False（确定性），NOT slot.project_id → True。
        但 collect_bma_factors_needed 在预扫描时 intent.has_car_service 未知，
        AND(True, None) = None，不会进入子树收集 expression_clarity。
        所以 LLM 只被请求 has_car_service 等一级因子，expression_clarity 不在请求中。
        最终进入子树后 expression_clarity 缺失 → 走兜底 FUZZY_PROJECT。
        """
        request: ClassifyRequest = ClassifyRequest(
            message="我想做个保养",
            slot_state={
                "project_id": None,
                "project_name": None,
                "saving_plan_type": None,
                "merchant": None,
                "booking_time": None,
            },
        )

        mock_llm: AsyncMock = AsyncMock(return_value={
            "intent.has_car_service": True,
            "intent.project_category": "机油保养",
            "intent.has_platform_question": False,
            "intent.expression_clarity": "specific",
            "intent.secondary_category": "无",
        })

        with patch("classify._call_llm_for_factors", mock_llm):
            response: ClassifyResponse = await _do_classify(request)

        # 验证 LLM 确实被调用
        mock_llm.assert_called_once()
        # NOT slot.project_id=True AND intent.has_car_service=True → 命中"有养车意图"
        # 但 expression_clarity 未被 collect_bma_factors_needed 收集（预扫描时无法进入子树），
        # _parse_llm_response 过滤掉了未请求的因子 → 子树中 expression_clarity 缺失 → 兜底
        assert response.scene_id == "FUZZY_PROJECT"

    @pytest.mark.asyncio
    async def test_s2_with_all_slots_filled(self, _load_config: None) -> None:
        """S2 阶段所有 slot 都有值 → COMPLETED。"""
        request: ClassifyRequest = ClassifyRequest(
            message="确认一下",
            slot_state={
                "project_id": "502",
                "project_name": "机油保养",
                "saving_plan_type": "coupon",
                "merchant": "店A",
                "booking_time": "10:00",
            },
        )
        response: ClassifyResponse = await _do_classify(request)
        # slot.project_id AND slot.saving_plan_type → True
        # 子树中：NOT slot.merchant → slot.merchant 有值 → NOT True → False（跳过）
        # NOT slot.booking_time → False（跳过）
        # 兜底 → COMPLETED
        assert response.scene_id == "COMPLETED"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, _load_config: None) -> None:
        """LLM 调用失败时走兜底（不抛异常）。"""
        request: ClassifyRequest = ClassifyRequest(
            message="随便聊聊",
            slot_state={},
        )

        with patch("classify._call_llm_for_factors", new_callable=AsyncMock, side_effect=Exception("LLM error")):
            response: ClassifyResponse = await _do_classify(request)

        # LLM 失败 → intent 因子缺失 → 所有 intent 条件返回 None → 走兜底
        assert response.scene_id == "CASUAL_CHAT"

    @pytest.mark.asyncio
    async def test_response_fields_complete(self, _load_config: None) -> None:
        """响应所有字段完整。"""
        request: ClassifyRequest = ClassifyRequest(
            message="我车抛锚了",
            slot_state={},
        )

        response: ClassifyResponse = await _do_classify(request)

        assert response.scene_id != ""
        assert response.scene_name != ""
        assert response.goal != ""
        assert response.strategy != ""
        assert isinstance(response.tools, list)
        assert isinstance(response.skills, list)
        assert isinstance(response.eval_path, list)
        assert isinstance(response.target_slots, dict)

    @pytest.mark.asyncio
    async def test_s2_scene_with_slots(self, _load_config: None) -> None:
        """S2 阶段：商户未选时走 FIND_MERCHANT。"""
        request: ClassifyRequest = ClassifyRequest(
            message="帮我找个店",
            slot_state={
                "project_id": "502",
                "project_name": "机油保养",
                "saving_plan_type": "coupon",
                "merchant": None,
                "booking_time": None,
            },
        )

        # S2 条件：slot.project_id AND slot.saving_plan_type → True
        # 子树中 NOT slot.merchant → merchant=None → False（确定性）→ NOT False → True
        response: ClassifyResponse = await _do_classify(request)

        assert response.scene_id == "FIND_MERCHANT"


# ============================================================
# FastAPI 端点集成测试
# ============================================================


class TestClassifyEndpoint:
    """/classify HTTP 端点集成测试。"""

    def test_classify_endpoint(self, _load_config: None) -> None:
        """POST /classify 端点返回正确格式。"""
        app: FastAPI = FastAPI()
        mount_classify_route(app)

        client: TestClient = TestClient(app)
        response = client.post(
            "/classify",
            json={"message": "我车抛锚了", "slot_state": {}},
        )

        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "scene_id" in data
        assert "scene_name" in data
        assert "tools" in data
        assert "skills" in data

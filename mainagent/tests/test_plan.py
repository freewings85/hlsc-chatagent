"""planagent（/plan 端点）smoke tests。

覆盖：
- DSL Pydantic 校验（合法 / 重复 id / 悬空 depends_on）
- plan_loader.build_plan_system_prompt：单场景 / 复合场景 / 未知场景
- create_agent_app() 跑完不 crash 且 /plan 路由已挂

不覆盖真实 LLM 调用 —— 那需要 pydantic-ai FunctionModel mock，后续迭代再补。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.dsl_models import ActionDef, Plan
from src.plan_loader import PlanSceneNotFoundError, build_plan_system_prompt


# ──────────────────────── DSL 校验 ────────────────────────


def test_plan_accepts_valid_dag() -> None:
    payload: dict[str, Any] = {
        "plan_id": "p-1",
        "nodes": [
            {"id": "a", "action": "fetch_user_profile", "depends_on": []},
            {"id": "b", "action": "search_shops_by_geo", "depends_on": ["a"]},
            {"id": "c", "action": "render_reply", "depends_on": ["b"]},
        ],
        "initial_inputs": {"user_query": "找店"},
    }
    plan: Plan = Plan.model_validate(payload)
    assert plan.plan_id == "p-1"
    assert len(plan.nodes) == 3
    assert plan.nodes[1].depends_on == ["a"]


def test_plan_rejects_duplicate_ids() -> None:
    payload: dict[str, Any] = {
        "plan_id": "p-1",
        "nodes": [
            {"id": "a", "action": "x", "depends_on": []},
            {"id": "a", "action": "y", "depends_on": []},
        ],
    }
    with pytest.raises(Exception) as exc:
        Plan.model_validate(payload)
    assert "重复" in str(exc.value)


def test_plan_rejects_dangling_dependency() -> None:
    payload: dict[str, Any] = {
        "plan_id": "p-1",
        "nodes": [
            {"id": "a", "action": "x", "depends_on": ["ghost"]},
        ],
    }
    with pytest.raises(Exception) as exc:
        Plan.model_validate(payload)
    assert "ghost" in str(exc.value)


# ──────────────────────── plan_loader 单场景 ────────────────────────


def test_plan_loader_single_scene_assembles_prompt() -> None:
    actions: list[ActionDef] = [
        ActionDef(name="fetch_user_profile", desc="拉画像"),
        ActionDef(name="search_shops_by_geo", desc="按位置搜"),
        ActionDef(name="render_reply", desc="出用户回复"),
    ]
    prompt: str = build_plan_system_prompt(["searchshops"], actions)

    # 四大块都在
    assert "话痨规划器" in prompt           # SYSTEM.md
    assert "规划方法论" in prompt           # PLAN_SOUL.md
    assert "业务目标" in prompt             # searchshops/PLAN_AGENT.md
    assert "输出规范" in prompt             # 根级 PLAN_OUTPUT.md
    # 单场景 header
    assert "单场景" in prompt
    # 白名单渲染
    assert "fetch_user_profile" in prompt
    assert "本次请求可用的动作" in prompt


def test_plan_loader_raises_on_unknown_scene() -> None:
    with pytest.raises(PlanSceneNotFoundError):
        build_plan_system_prompt(["this_scene_definitely_not_exists"], [])


def test_plan_loader_without_actions_still_builds() -> None:
    prompt: str = build_plan_system_prompt(["searchshops"], [])
    assert "话痨规划器" in prompt
    assert "本次请求可用的动作" not in prompt  # 空时不渲染表格


def test_plan_loader_rejects_empty_scenes() -> None:
    with pytest.raises(ValueError):
        build_plan_system_prompt([], [])


# ──────────────────────── plan_loader 复合场景 ────────────────────────


def test_plan_loader_composite_scenes_stack_agent_md() -> None:
    """复合场景：两个 PLAN_AGENT.md 顺序堆叠，PLAN_OUTPUT.md 只出现一次。"""
    actions: list[ActionDef] = [
        ActionDef(name="fetch_user_profile"),
        ActionDef(name="search_shops_by_geo"),
        ActionDef(name="search_coupons"),
        ActionDef(name="render_reply"),
    ]
    prompt: str = build_plan_system_prompt(["searchshops", "searchcoupons"], actions)

    # 两个场景的业务说明都在（按请求顺序）
    assert "场景 `searchshops` 业务说明" in prompt
    assert "场景 `searchcoupons` 业务说明" in prompt
    assert prompt.index("searchshops` 业务说明") < prompt.index("searchcoupons` 业务说明")

    # 复合场景 header
    assert "复合" in prompt
    assert "处理复合场景" in prompt

    # 输出规范只出现一次（没按场景重复）
    assert prompt.count("输出规范") == 1


def test_plan_loader_composite_unknown_scene_still_errors() -> None:
    """只要有一个场景不存在就报错，不会静默跳过。"""
    with pytest.raises(PlanSceneNotFoundError):
        build_plan_system_prompt(["searchshops", "ghost_scene"], [])


# ──────────────────────── app bootstrap ────────────────────────


def test_create_agent_app_mounts_plan_route() -> None:
    """冒烟：create_agent_app() 跑完且 /plan 被挂到 FastAPI 上。"""
    from src.app import create_agent_app

    agent_app = create_agent_app()
    routes: list[str] = [getattr(r, "path", "") for r in agent_app.app.routes]
    assert "/plan" in routes
    assert "/classify" in routes  # 回归：别把老端点弄丢了

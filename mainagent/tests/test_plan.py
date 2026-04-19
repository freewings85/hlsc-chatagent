"""planagent（/plan 端点）smoke tests。

覆盖：
- DSL Pydantic 校验（合法 / 重复 id / 悬空 depends_on）
- plan_loader.build_plan_system_prompt 能读到场景 prompts + 渲染 activity 表格
- create_agent_app() 跑完不 crash 且 /plan 路由已挂

不覆盖真实 LLM 调用 —— 那需要 pydantic-ai FunctionModel mock，后续迭代再补。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.dsl_models import ActivityDef, Plan
from src.plan_loader import PlanSceneNotFoundError, build_plan_system_prompt


# ──────────────────────── DSL 校验 ────────────────────────


def test_plan_accepts_valid_dag() -> None:
    payload: dict[str, Any] = {
        "plan_id": "p-1",
        "nodes": [
            {"id": "a", "activity": "fetch_user_profile", "depends_on": []},
            {"id": "b", "activity": "search_shops_by_geo", "depends_on": ["a"]},
            {"id": "c", "activity": "render_reply", "depends_on": ["b"]},
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
            {"id": "a", "activity": "x", "depends_on": []},
            {"id": "a", "activity": "y", "depends_on": []},
        ],
    }
    with pytest.raises(Exception) as exc:
        Plan.model_validate(payload)
    assert "重复" in str(exc.value)


def test_plan_rejects_dangling_dependency() -> None:
    payload: dict[str, Any] = {
        "plan_id": "p-1",
        "nodes": [
            {"id": "a", "activity": "x", "depends_on": ["ghost"]},
        ],
    }
    with pytest.raises(Exception) as exc:
        Plan.model_validate(payload)
    assert "ghost" in str(exc.value)


# ──────────────────────── plan_loader ────────────────────────


def test_plan_loader_renders_system_prompt_with_activities() -> None:
    activities: list[ActivityDef] = [
        ActivityDef(name="fetch_user_profile", desc="拉画像"),
        ActivityDef(name="search_shops_by_geo", desc="按位置搜"),
        ActivityDef(name="render_reply", desc="出用户回复"),
    ]
    prompt: str = build_plan_system_prompt("searchshops", activities)

    # 四大块都拼上了
    assert "话痨规划器" in prompt             # SYSTEM.md
    assert "规划方法论" in prompt             # PLAN_SOUL.md
    assert "业务目标" in prompt               # searchshops/PLAN_AGENT.md
    assert "输出规范" in prompt               # searchshops/PLAN_OUTPUT.md
    # 白名单表格渲染进来了
    assert "fetch_user_profile" in prompt
    assert "按位置搜" in prompt
    assert "本场景可用 activity" in prompt


def test_plan_loader_raises_on_unknown_scene() -> None:
    with pytest.raises(PlanSceneNotFoundError):
        build_plan_system_prompt("this_scene_definitely_not_exists", [])


def test_plan_loader_without_activities_still_builds() -> None:
    """即使白名单空，prompt 也能组装出来（LLM 会规划失败，但这是它的事）。"""
    prompt: str = build_plan_system_prompt("searchshops", [])
    assert "话痨规划器" in prompt
    assert "本场景可用 activity" not in prompt  # 空时不渲染表格


# ──────────────────────── app bootstrap ────────────────────────


def test_create_agent_app_mounts_plan_route() -> None:
    """冒烟：create_agent_app() 跑完且 /plan 被挂到 FastAPI 上。"""
    from src.app import create_agent_app

    agent_app = create_agent_app()
    routes: list[str] = [getattr(r, "path", "") for r in agent_app.app.routes]
    assert "/plan" in routes
    assert "/classify" in routes  # 回归：别把老端点弄丢了

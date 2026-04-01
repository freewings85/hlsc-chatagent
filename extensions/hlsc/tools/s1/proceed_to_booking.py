"""proceed_to_booking 工具：用户准备好进入下单流程，触发 S1 → S2 即时升级。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

SavingMethod = Literal["platform_offer", "insurance_bidding", "merchant_promo", "none"]

_DESCRIPTION: str = load_tool_prompt("proceed_to_booking")


async def proceed_to_booking(
    ctx: RunContext[AgentDeps],
    project_id: Annotated[str, Field(description="项目标识（来自 classify_project 返回的 project_id，保险类固定为 '9999'）")],
    project_name: Annotated[str, Field(description="项目名称（来自 classify_project 返回的 project_name，保险类固定为 '保险项目'）")],
    saving_method: Annotated[SavingMethod | None, Field(description="用户选择的省钱方式：platform_offer（平台优惠）/ insurance_bidding（保险竞价）/ merchant_promo（商户优惠）/ none（不需要优惠）/ 不传表示用户未明确选择")] = None,
) -> str:
    """进入下单流程，记录项目和省钱方式，即时扩展预订能力。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, str | None] = {
        "project_id": project_id,
        "project_name": project_name,
        "saving_method": saving_method,
    }
    log_tool_start("proceed_to_booking", sid, rid, params)

    # 1. 写入硬信号：升级到 S2
    from hlsc.services.user_stat_service import user_stat_service

    await user_stat_service.upgrade_to_s2(ctx.deps.user_id)

    # 2. 即时切换 deps — 不等下一轮，同轮生效
    from src.business_map_hook import _config_loader

    _config_loader.ensure_loaded()
    s2_config = _config_loader.get_stage("S2")
    ctx.deps.current_stage = "S2"
    ctx.deps.available_tools = s2_config.tools
    ctx.deps.allowed_skills = s2_config.skills

    # 3. 加载 S2 的 system prompt，写入 deps 让 loop 下次 ModelRequestNode 前替换
    templates_dir: Path = Path(__file__).resolve().parents[4] / "mainagent" / "prompts" / "templates"
    parts: list[str] = ["SYSTEM.md", "SOUL.md", "OUTPUT.md", "AGENT_S2.md"]
    system_prompt: str = "\n\n".join(
        (templates_dir / p).read_text(encoding="utf-8").strip()
        for p in parts if (templates_dir / p).exists()
    )
    ctx.deps.system_prompt_override = system_prompt

    # 构建返回值
    method_names: dict[str, str] = {
        "platform_offer": "平台优惠方式",
        "insurance_bidding": "保险竞价",
        "merchant_promo": "商户自有优惠",
        "none": "无特定省钱方式",
    }
    method_label: str = method_names.get(saving_method or "", "未指定省钱方式")

    result: str = f"已确认：项目「{project_name}」，省钱方式「{method_label}」。系统已扩展预订下单能力。"
    log_tool_end("proceed_to_booking", sid, rid, {"result": result})
    return result


proceed_to_booking.__doc__ = _DESCRIPTION

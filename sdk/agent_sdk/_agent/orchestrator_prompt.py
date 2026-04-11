"""Orchestrator 编排模式的系统提示词渲染。

对应 orchestrator-design.md §8.4。把 workflow 的骨架状态和当前 step 详情渲染成
一段可读的 system prompt 注入到 LLM 上下文里。

不能把全部细节塞进来——prompt 长度控制，重点：
- 全局骨架（让 Agent 知道自己在整个流程的什么位置）
- 当前 step 的目标 + 成功判据 + 需要收集的字段
- allowed_next（Workflow 已经按 requires 过滤过）
- step_pending_fields（温和提醒哪些字段还没齐）
- 推进规则（强约束：工具返回非 ok 时必须如实告诉用户）
"""

from __future__ import annotations

from typing import Any


def render_orchestrator_prompt(
    step_skeleton: list[dict[str, Any]],
    current_step: dict[str, Any],
    completed_steps: list[str],
    session_state: dict[str, Any],
    step_pending_fields: list[str],
) -> str:
    """渲染 orchestrator 编排上下文。"""
    parts: list[str] = []

    # 全局骨架
    if step_skeleton:
        parts.append("## 当前场景 Workflow 全局骨架")
        parts.append("")
        parts.append(_render_skeleton(step_skeleton))
        parts.append("")

    # 当前 step 详情
    parts.append("## 当前聚焦 Step")
    parts.append("")
    parts.append(f"- **Step ID**: {current_step.get('id', '')}")
    parts.append(f"- **名称**: {current_step.get('name', '')}")
    parts.append(f"- **目标**: {current_step.get('goal', '')}")
    parts.append(f"- **完成标准**: {current_step.get('success_criteria', '')}")
    parts.append(
        f"- **需要收集的字段**: {_render_fields(current_step.get('expected_fields', []))}"
    )
    allowed_next: list[str] = current_step.get("allowed_next") or []
    parts.append(
        f"- **允许的下一步**: {', '.join(allowed_next) if allowed_next else '(END)'}"
    )
    skip_hint: str | None = current_step.get("skip_hint")
    if skip_hint:
        parts.append(f"- **跳过提示**: {skip_hint}")
    parts.append("")

    # 会话状态
    parts.append("## 已收集的会话状态")
    parts.append("")
    parts.append(_render_session_state(session_state))
    parts.append("")

    # 待收集字段（温和提醒）
    parts.append("## 当前 Step 待收集字段")
    parts.append("")
    parts.append(_render_pending_fields(step_pending_fields))
    parts.append("")

    # 推进规则
    parts.append("## 推进规则")
    parts.append("")
    parts.append(
        "- **收集到 current_step.expected_fields 中的全部字段后**，必须调用 "
        "`update_session_state(updates={...}, advance_to=<next_step_id>)` 工具把"
        "字段写入并声明推进"
    )
    parts.append(
        "- `advance_to` 必须在 `allowed_next` 里；`END` 表示整个流程结束"
    )
    parts.append(
        "- 如果用户改变主意要回到之前的步骤，调 "
        "`update_session_state(updates={}, revert_to=<step_id>, revert_reason=...)`"
    )
    parts.append(
        "- **不要**擅自声称完成了某个 step —— 没调 `update_session_state` 就不算数"
    )
    parts.append(
        "- **工具返回值必须信**：工具返回以 `error:` 或大写错误码开头时"
        "（如 `MISSING_FIELDS:...` / `ILLEGAL_TRANSITION:...`），说明推进被拒，"
        "本轮 final 必须如实告诉用户缺了什么，**不能假装已完成**"
    )
    parts.append(
        "- **同 turn 内最多推进一次**：advance/revert 成功后不要在同一 turn 再"
        "调 `update_session_state` 做第二次推进，直接生成 final 回复结束本轮"
    )

    return "\n".join(parts)


# ── 渲染辅助 ───────────────────────────────────────────────


def _render_skeleton(skeleton: list[dict[str, Any]]) -> str:
    """渲染全局骨架：
        ✓ collect_info     收集投保信息
        * propose_quotes   出价与推送          ← 当前
        ○ ...
    """
    lines: list[str] = []
    for brief in skeleton:
        status: str = brief.get("status", "pending")
        marker: str = {"done": "✓", "current": "*", "pending": "○"}.get(status, "○")
        suffix: str = "        ← 当前" if status == "current" else ""
        sid: str = brief.get("id", "")
        goal_short: str = brief.get("goal_short", "")
        lines.append(f"{marker} {sid:<20}{goal_short}{suffix}")
    return "\n".join(lines)


def _render_fields(fields: list[dict[str, str]]) -> str:
    if not fields:
        return "(无)"
    return ", ".join(f"{f.get('name', '')}:{f.get('type', '')}" for f in fields)


def _render_session_state(state: dict[str, Any]) -> str:
    if not state:
        return "(空)"
    pairs: list[str] = []
    for k, v in state.items():
        if v is None:
            continue
        v_str: str = str(v)
        if len(v_str) > 100:
            v_str = v_str[:100] + "..."
        pairs.append(f"- {k} = {v_str}")
    return "\n".join(pairs) if pairs else "(空)"


def _render_pending_fields(pending: list[str]) -> str:
    if not pending:
        return (
            "(无，当前 step 的必填字段都已齐备，"
            "可以调 update_session_state 推进)"
        )
    return (
        f"💡 当前 step 还需要：{', '.join(pending)}\n\n"
        f"在合适的时机自然地向用户询问这些信息，**不要打断用户正在问的话题**。"
        f"如果用户本轮问的是别的事，先正常回答再伺机询问。"
    )

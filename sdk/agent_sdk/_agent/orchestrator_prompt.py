"""Orchestrator 编排模式的动态上下文渲染（v2）。

设计原则：
- Checklist 作为唯一的字段状态视图（合并 expected_fields + session_state + pending）
- 进度条一行（不展开非当前 step 的 goal）
- 只渲染动态数据，静态行为准则放 AGENT.md
- ~100 token/轮，比 v1（~400 token）节省 75%
"""

from __future__ import annotations

from typing import Any

# 值截断阈值
_VALUE_MAX: int = 40


def render_orchestrator_prompt(
    step_skeleton: list[dict[str, Any]],
    current_step: dict[str, Any],
    session_state: dict[str, Any],
    step_pending_fields: list[str],
    scenario_label: str = "",
) -> str:
    """渲染 orchestrator 编排上下文。"""
    parts: list[str] = []

    # ── 进度条（一行）──
    progress: str = _render_progress(step_skeleton, scenario_label)
    if progress:
        parts.append(progress)
        parts.append("")

    # ── 当前目标 ──
    goal: str = current_step.get("goal", "")
    if goal:
        parts.append(f"## 目标\n{goal}")
        parts.append("")

    # ── Checklist ──
    checklist: str = _render_checklist(
        current_step.get("expected_fields", []),
        session_state,
        step_pending_fields,
    )
    if checklist:
        parts.append(f"## Checklist\n{checklist}")
        parts.append("")

    # ── 指令行 ──
    hint: str = _render_action_hint(step_pending_fields)
    if hint:
        parts.append(hint)

    return "\n".join(parts)


# ── 渲染辅助 ───────────────────────────────────────────────


def _render_progress(
    skeleton: list[dict[str, Any]],
    scenario_label: str,
) -> str:
    """一行进度：## 进度：保险竞价 [1/2]\n✓ 收集信息 → * 生成报价"""
    if not skeleton:
        return ""

    total: int = len(skeleton)
    current_idx: int = 0
    markers: list[str] = []

    for i, brief in enumerate(skeleton):
        status: str = brief.get("status", "pending")
        name: str = brief.get("name", brief.get("id", ""))
        if status == "done":
            markers.append(f"✓ {name}")
        elif status == "current":
            current_idx = i + 1
            markers.append(f"* {name}")
        else:
            markers.append(f"○ {name}")

    # 超过 5 步时折叠远端 pending
    if total > 5:
        keep: int = current_idx + 1
        if keep < total:
            remaining: int = total - keep
            markers = markers[:keep] + [f"○ ...({remaining} 步)"]

    label: str = f"：{scenario_label}" if scenario_label else ""
    return f"## 进度{label} [{current_idx}/{total}]\n" + " → ".join(markers)


def _render_checklist(
    expected_fields: list[dict[str, str]],
    session_state: dict[str, Any],
    pending: list[str],
) -> str:
    """渲染 [x]/[ ] checklist。"""
    if not expected_fields:
        return ""

    pending_set: set[str] = set(pending)
    lines: list[str] = []

    for f in expected_fields:
        name: str = f.get("name", "")
        label: str = f.get("label", "")
        display: str = f"{name}（{label}）" if label else name

        if name not in pending_set:
            value: Any = session_state.get(name)
            value_str: str = _format_value(value)
            lines.append(f"- [x] {display} = {value_str}")
        else:
            lines.append(f"- [ ] {display}")

    return "\n".join(lines)


def _format_value(value: Any) -> str:
    """短值完整显示，长值截断。"""
    if value is None:
        return "(已收集)"
    s: str = str(value)
    if len(s) <= _VALUE_MAX:
        return s
    return s[:_VALUE_MAX] + "..."


def _render_action_hint(pending: list[str]) -> str:
    """Checklist 下方的指令行。"""
    if pending:
        return "→ 从用户消息中提取信息后及时调 update_workflow_state 写入，不必等全部收齐"
    return "→ 全部字段已齐，调 update_workflow_state(fields={...}) 写入"

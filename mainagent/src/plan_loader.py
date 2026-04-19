"""规划器 system prompt 拼装：纯函数，不依赖 deps。

和 mainagent 主对话的 prompt_loader 不同：
- 不走 stage_config.yaml（plan 场景不进 mainagent 的场景配置，避免字段撞车）
- 场景结构固定约定：prompts/templates/plan/{SYSTEM.md,PLAN_SOUL.md} + plan/{scene}/{PLAN_AGENT.md,PLAN_OUTPUT.md}
- 动态：available_activities 清单由调用方传入，渲染成 markdown 表格拼在 agent_md 末尾
"""

from __future__ import annotations

from pathlib import Path

from src.dsl_models import ActivityDef


# plan 专用 prompt 根目录
_PLAN_TEMPLATES_DIR: Path = (
    Path(__file__).resolve().parent.parent / "prompts" / "templates" / "plan"
)


class PlanSceneNotFoundError(Exception):
    """请求的 plan 场景目录不存在。"""


def _read_file(relative_path: str) -> str:
    path: Path = _PLAN_TEMPLATES_DIR / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _format_activities_block(activities: list[ActivityDef]) -> str:
    """把 available_activities 渲染成 markdown 表格拼到 agent_md 尾部。

    规划器 LLM 必须看到这个清单才能生成合法 DSL。
    """
    if not activities:
        return ""

    lines: list[str] = [
        "",
        "## 本场景可用 activity（白名单，严格，不可臆造）",
        "",
        "| activity | 说明 |",
        "|---|---|",
    ]
    for a in activities:
        desc: str = a.desc.replace("|", "\\|")
        lines.append(f"| `{a.name}` | {desc} |")
    return "\n".join(lines)


def build_plan_system_prompt(
    scene: str,
    activities: list[ActivityDef],
) -> str:
    """拼装 plan LLM 的 system prompt。

    顺序：SYSTEM.md → PLAN_SOUL.md → {scene}/PLAN_AGENT.md → {scene}/PLAN_OUTPUT.md
          → 动态白名单表格
    """
    scene_dir: Path = _PLAN_TEMPLATES_DIR / scene
    if not scene_dir.is_dir():
        raise PlanSceneNotFoundError(
            f"plan 场景 '{scene}' 在 {_PLAN_TEMPLATES_DIR} 下没有对应目录"
        )

    parts: list[str] = []
    for rel in ["SYSTEM.md", "PLAN_SOUL.md", f"{scene}/PLAN_AGENT.md", f"{scene}/PLAN_OUTPUT.md"]:
        content: str = _read_file(rel)
        if content:
            parts.append(content)

    activities_block: str = _format_activities_block(activities)
    if activities_block:
        parts.append(activities_block)

    return "\n\n".join(parts)

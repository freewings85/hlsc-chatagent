"""规划器 system prompt 拼装：纯函数，不依赖 deps。

接收 **场景列表**（来自 BMA 分类），支持单场景和复合场景：
- 共享文件：plan/{SYSTEM.md, PLAN_SOUL.md, PLAN_OUTPUT.md}
- 场景特化：plan/{scene}/PLAN_AGENT.md（只讲"本场景业务语义"）
- 复合场景 = 多个 scene 的 PLAN_AGENT.md 顺序堆叠；输出规范和方法论文件全局只有一份

available_actions 清单由调用方传入（orchestrator 已对多场景做 union），
渲染成 markdown 表格拼到 prompt 末尾。
"""

from __future__ import annotations

from pathlib import Path

from src.dsl_models import ActionDef


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


def _format_actions_block(actions: list[ActionDef]) -> str:
    """把 available_actions 渲染成 markdown 表格拼到 prompt 尾部。

    规划器 LLM 必须看到这个清单才能生成合法 DSL。orchestrator 侧多场景 union
    的动作已经在请求里完成，本模块只做渲染。
    """
    if not actions:
        return ""

    lines: list[str] = [
        "",
        "## 本次请求可用的动作（白名单，严格，不可臆造）",
        "",
        "| action | 说明 |",
        "|---|---|",
    ]
    for a in actions:
        desc: str = a.desc.replace("|", "\\|")
        lines.append(f"| `{a.name}` | {desc} |")
    return "\n".join(lines)


def _format_scenes_header(scenes: list[str]) -> str:
    """告诉 LLM 本次是单场景还是复合场景。"""
    if len(scenes) == 1:
        return f"## 本次规划场景\n\n- `{scenes[0]}`（单场景）"
    return (
        "## 本次规划场景（复合）\n\n"
        + "\n".join(f"- `{s}`" for s in scenes)
        + "\n\n注意：这是一个**复合任务**，不是多个独立任务。参见 PLAN_SOUL 里"
        + "「处理复合场景」一节的守则。"
    )


def build_plan_system_prompt(
    scenes: list[str],
    actions: list[ActionDef],
) -> str:
    """拼装 plan LLM 的 system prompt。

    顺序：
      SYSTEM.md
      PLAN_SOUL.md
      <本次场景 header>
      {scene_1}/PLAN_AGENT.md
      {scene_2}/PLAN_AGENT.md
      ...
      PLAN_OUTPUT.md        ← 根级，全局通用
      <白名单表格>

    Args:
        scenes: 场景 id 列表；长度 >=1，单场景时长度 1
        actions: 动作白名单（orchestrator 侧已做 union）

    Raises:
        PlanSceneNotFoundError: 任一 scene 在 plan/ 下没有对应目录
        ValueError: scenes 为空
    """
    if not scenes:
        raise ValueError("scenes 不能为空")

    # 预校验所有场景目录都存在，提前暴露
    for scene in scenes:
        scene_dir: Path = _PLAN_TEMPLATES_DIR / scene
        if not scene_dir.is_dir():
            raise PlanSceneNotFoundError(
                f"plan 场景 '{scene}' 在 {_PLAN_TEMPLATES_DIR} 下没有对应目录"
            )

    parts: list[str] = []

    # 共享前置
    for rel in ["SYSTEM.md", "PLAN_SOUL.md"]:
        content: str = _read_file(rel)
        if content:
            parts.append(content)

    # 场景 header
    parts.append(_format_scenes_header(scenes))

    # 各场景的业务说明（顺序堆叠）
    for scene in scenes:
        content = _read_file(f"{scene}/PLAN_AGENT.md")
        if content:
            parts.append(f"# 场景 `{scene}` 业务说明\n\n" + content)

    # 共享输出规范（根级单份）
    output_spec: str = _read_file("PLAN_OUTPUT.md")
    if output_spec:
        parts.append(output_spec)

    # 动态 action 白名单
    actions_block: str = _format_actions_block(actions)
    if actions_block:
        parts.append(actions_block)

    return "\n\n".join(parts)

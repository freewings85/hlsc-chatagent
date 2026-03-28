"""update_state_tree 可靠性重复验证脚本。

对 S2 场景（节点完成 -> update_state_tree 调用）执行 5 次重复运行，
收集每次运行的详细结果，生成可靠性证据报告。

使用方式：
    export PATH="/home/leo/.local/bin:$PATH"
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    set -a && source mainagent/.env.local && set +a
    uv run python reports/run_update_state_tree_reliability.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "mainagent"))
sys.path.insert(0, str(_PROJECT_ROOT / "extensions"))
sys.path.insert(0, str(_PROJECT_ROOT / "sdk"))

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model

from agent_sdk._agent.model import create_model
from hlsc.services.business_map_service import BusinessMapService


# ============================================================
# 常量
# ============================================================

TOTAL_RUNS: int = 5


# ============================================================
# 类型定义
# ============================================================


@dataclass
class ToolCallRecord:
    """工具调用记录"""

    tool_name: str
    args: dict[str, Any]


@dataclass
class SingleRunResult:
    """单次运行结果"""

    run_number: int
    tool_calls: list[ToolCallRecord]
    agent_response: str
    update_called: bool
    content_has_completion: bool
    passed: bool
    elapsed_seconds: float


# ============================================================
# 业务地图加载
# ============================================================


def load_business_map() -> BusinessMapService:
    """加载业务地图 YAML 并返回服务实例。"""
    biz_map_dir: Path = _PROJECT_ROOT / "mainagent" / "business-map"
    svc: BusinessMapService = BusinessMapService()
    svc.load(biz_map_dir)
    return svc


# ============================================================
# Agent 工厂
# ============================================================


def load_system_prompt_parts() -> str:
    """加载 SYSTEM.md + SOUL.md + OUTPUT.md 并拼接。"""
    templates_dir: Path = _PROJECT_ROOT / "mainagent" / "prompts" / "templates"
    parts: list[str] = []
    for filename in ["SYSTEM.md", "SOUL.md", "OUTPUT.md"]:
        path: Path = templates_dir / filename
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def load_agent_md() -> str:
    """读取 AGENT.md 内容。"""
    agent_md_path: Path = (
        _PROJECT_ROOT / "mainagent" / "prompts" / "templates" / "AGENT.md"
    )
    return agent_md_path.read_text(encoding="utf-8").strip()


def build_system_prompt() -> str:
    """组装完整的系统提示词（SYSTEM + SOUL + OUTPUT + AGENT）。"""
    system_parts: str = load_system_prompt_parts()
    agent_md: str = load_agent_md()
    return f"{system_parts}\n\n{agent_md}"


_BUSINESS_MAP_INSTRUCTIONS: str = """[business_map_instructions]:
切片解读：每个 ### 段落是一个业务节点，按层级从浅到深排列。多路径用 --- 分隔。
状态标记：[完成] → 产出 / [进行中] ← 当前 / [跳过] / [ ] 未开始

使用原则：
- 切片是主要参考，优先按 checklist 推进；但如果用户意图明显偏离切片内容，以用户为准
- 用户确认、完成步骤、做出选择后，先调用 update_state_tree 保存进度，再回复用户
- 需要更多节点详情时调用 read_business_node
- 闲聊或无业务进展时不需要更新状态树""".strip()


def build_user_message_with_context(
    user_message: str,
    slice_md: str,
    state_tree: str,
) -> str:
    """构造包含 request_context + business_map_instructions + slice + state_tree 的用户消息。"""
    context_parts: list[str] = [
        "[request_context]: current_car: 2021款大众朗逸 1.5L, current_location: (未设置)",
    ]
    if slice_md or state_tree:
        context_parts.append(_BUSINESS_MAP_INSTRUCTIONS)
    if slice_md:
        context_parts.append(f"[business_map_slice]:\n{slice_md}")
    if state_tree:
        context_parts.append(f"[state_tree]:\n{state_tree}")

    context_block: str = "\n\n".join(context_parts)
    return f"{context_block}\n\n{user_message}"


# ============================================================
# 单次运行
# ============================================================


async def run_single(
    run_number: int,
    user_message: str,
    slice_md: str,
    state_tree: str,
    biz_svc: BusinessMapService,
) -> SingleRunResult:
    """执行 S2 场景的一次运行。"""
    # 追踪工具调用
    tool_calls: list[ToolCallRecord] = []

    # 构建 pydantic_ai Agent（每次新建以避免状态污染）
    model: Model = create_model()
    system_prompt: str = build_system_prompt()

    agent: Agent[None, str] = Agent(
        model=model,
        system_prompt=system_prompt,
    )

    # 注册 mock 工具
    @agent.tool_plain
    async def update_state_tree(
        content: str,
    ) -> str:
        """保存业务进度。用户确认、完成步骤、做出选择后必须立即调用，否则进度丢失。

        调用时机（满足任一即调用）：
        - 用户确认了项目或选项 → 标记 [完成] + → 产出
        - 完成或跳过某节点 → 标记 [完成]/[跳过]
        - 开始处理新节点 → 标记 [进行中] + ← 当前

        content 参数：传入更新后的完整状态树（缩进 Markdown 格式）。
        """
        tool_calls.append(ToolCallRecord(
            tool_name="update_state_tree",
            args={"content": content},
        ))
        return "状态树已更新"

    @agent.tool_plain
    async def read_business_node(
        node_id: str,
    ) -> str:
        """查看指定业务节点的完整业务定义。

        返回该节点的 description、checklist、output、depends_on、cancel_directions 等内容。
        当切片中提到某个节点需要进一步了解、或需要查看某节点的具体 checklist 和取消走向时使用。
        """
        tool_calls.append(ToolCallRecord(
            tool_name="read_business_node",
            args={"node_id": node_id},
        ))
        try:
            result: str = biz_svc.get_business_node_detail(node_id)
        except KeyError:
            result = f"节点 '{node_id}' 不存在于业务地图中。"
        return result

    # 构造用户消息
    full_message: str = build_user_message_with_context(
        user_message, slice_md, state_tree,
    )

    # 执行
    start_time: float = time.time()
    result = await agent.run(full_message)
    elapsed: float = time.time() - start_time

    agent_response: str = result.output

    # 判定结果
    update_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "update_state_tree"
    ]
    update_called: bool = len(update_calls) > 0

    content_has_completion: bool = False
    if update_calls:
        content: str = update_calls[0].args.get("content", "")
        content_has_completion = "[完成]" in content

    passed: bool = update_called and content_has_completion

    return SingleRunResult(
        run_number=run_number,
        tool_calls=tool_calls,
        agent_response=agent_response,
        update_called=update_called,
        content_has_completion=content_has_completion,
        passed=passed,
        elapsed_seconds=elapsed,
    )


# ============================================================
# 输出格式化
# ============================================================


def format_single_run(run_result: SingleRunResult, slice_md: str, state_tree: str) -> str:
    """格式化单次运行结果。"""
    lines: list[str] = []
    status: str = "PASS" if run_result.passed else "FAIL"

    lines.append(f"=== Run {run_result.run_number}/{TOTAL_RUNS} ===")
    lines.append(f"Result: {status}")
    lines.append(f"update_state_tree called: {'YES' if run_result.update_called else 'NO'}")
    lines.append(f"content contains [完成]: {'YES' if run_result.content_has_completion else 'NO'}")
    lines.append(f"Elapsed: {run_result.elapsed_seconds:.1f}s")
    lines.append("")

    # 工具调用列表
    if run_result.tool_calls:
        lines.append(f"Tool calls ({len(run_result.tool_calls)}):")
        for tc in run_result.tool_calls:
            args_display: dict[str, Any] = {}
            for k, v in tc.args.items():
                if isinstance(v, str) and len(v) > 300:
                    args_display[k] = v[:300] + "..."
                else:
                    args_display[k] = v
            lines.append(f"  - {tc.tool_name}({json.dumps(args_display, ensure_ascii=False)})")
    else:
        lines.append("Tool calls: none")
    lines.append("")

    # Agent 回复
    lines.append(f"Agent response:\n{run_result.agent_response}")
    lines.append("")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行 S2 场景 5 次并输出可靠性证据。"""
    print(f"update_state_tree 可靠性重复验证 — {TOTAL_RUNS} 次运行")
    print("加载业务地图...")

    biz_svc: BusinessMapService = load_business_map()
    print("业务地图加载完成")
    print("")

    # S2 场景参数
    user_message: str = "对，就做小保养，换机油和机滤就行，确认了"

    # 组装切片：confirm_project / direct_expression
    slice_md: str = biz_svc.assemble_slice(["direct_expression"])

    # 带已完成 checklist 项的状态树
    state_tree: str = textwrap.dedent("""\
        - [进行中] 沟通项目需求与省钱方案
          - [进行中] 确认养车项目
            - [进行中] 直接表达场景
              - [完成] 识别车主提到的具体项目名称 → 小保养（换机油+机滤）
              - [完成] 确认项目与车型匹配 → 2021款大众朗逸 1.5L，项目匹配
              - [进行中] 获得车主最终确认 ← 当前
          - [ ] 确认特殊需求
          - [ ] 确认省钱方法
        - [ ] 筛选匹配商户
        - [ ] 执行预订""")

    # 运行 5 次
    run_results: list[SingleRunResult] = []
    output_parts: list[str] = []

    # 报告头
    output_parts.append("update_state_tree 可靠性重复验证证据")
    output_parts.append(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    output_parts.append(f"场景: S2 (node completion -> update_state_tree call)")
    output_parts.append(f"用户消息: {user_message}")
    output_parts.append(f"重复次数: {TOTAL_RUNS}")
    output_parts.append(f"评分规则: PASS = update_state_tree called AND content contains [完成]")
    output_parts.append("")
    output_parts.append(f"注入切片（前200字）:\n{slice_md[:200]}...")
    output_parts.append("")
    output_parts.append(f"注入状态树:\n{state_tree}")
    output_parts.append("")

    # 环境信息
    llm_type: str = os.getenv("LLM_TYPE", "unknown")
    deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", os.getenv("LLM_MODEL", "unknown"))
    output_parts.append(f"模型: {llm_type} / {deployment}")
    output_parts.append("")
    output_parts.append("=" * 70)
    output_parts.append("")

    for run_num in range(1, TOTAL_RUNS + 1):
        print(f"运行 {run_num}/{TOTAL_RUNS} ...")

        run_result: SingleRunResult = await run_single(
            run_number=run_num,
            user_message=user_message,
            slice_md=slice_md,
            state_tree=state_tree,
            biz_svc=biz_svc,
        )
        run_results.append(run_result)

        status: str = "PASS" if run_result.passed else "FAIL"
        print(f"  [{status}] update_called={'YES' if run_result.update_called else 'NO'}, "
              f"has_completion={'YES' if run_result.content_has_completion else 'NO'}, "
              f"耗时 {run_result.elapsed_seconds:.1f}s")

        # 添加到输出
        output_parts.append(format_single_run(run_result, slice_md, state_tree))

    # 汇总
    total_passed: int = sum(1 for r in run_results if r.passed)
    total_update_called: int = sum(1 for r in run_results if r.update_called)

    summary_lines: list[str] = [
        "=" * 70,
        "",
        f"Repeated-run summary (S2: node completion -> update_state_tree):",
        f"- Runs: {TOTAL_RUNS}",
        f"- Passes: {total_passed}/{TOTAL_RUNS}",
        f"- update_state_tree call rate: {total_update_called}/{TOTAL_RUNS}",
        f"- Scoring rule: PASS = update_state_tree called AND content contains [完成]",
        "",
        "Per-run breakdown:",
    ]

    for r in run_results:
        summary_lines.append(
            f"  Run {r.run_number}: {'PASS' if r.passed else 'FAIL'} "
            f"(update_called={'YES' if r.update_called else 'NO'}, "
            f"has_completion={'YES' if r.content_has_completion else 'NO'}, "
            f"elapsed={r.elapsed_seconds:.1f}s)"
        )

    summary_lines.append("")
    summary_lines.append(f"模型: {llm_type} / {deployment}")
    summary_lines.append(f"评分方式: update_state_tree 是否被调用 + 内容是否包含 [完成]")

    output_parts.extend(summary_lines)

    full_output: str = "\n".join(output_parts)

    print("")
    print(full_output)

    # 保存到文件
    output_path: Path = _PROJECT_ROOT / "reports" / "update-state-tree-reliability-evidence.txt"
    output_path.write_text(full_output, encoding="utf-8")
    print(f"\n报告已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

"""read_business_node 路径验证脚本：使用真实 LLM 证明 read_business_node 被调用。

场景 S5：切片中包含 confirm_saving 节点信息和子节点引用 (coupon_path, bidding_path)，
但不包含这些子节点的详细内容。用户询问优惠券和竞价各自的详细操作方式，
迫使模型调用 read_business_node 获取子节点完整定义。

使用方式：
    export PATH="/home/leo/.local/bin:$PATH"
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    set -a && source mainagent/.env.local && set +a
    uv run python reports/run_read_business_node_eval.py
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
# 类型定义
# ============================================================


@dataclass
class ToolCallRecord:
    """工具调用记录"""

    tool_name: str
    args: dict[str, Any]
    result: str


@dataclass
class CheckResult:
    """单项检查结果"""

    label: str
    passed: bool
    detail: str


@dataclass
class ScenarioResult:
    """单个场景的评估结果"""

    name: str
    description: str
    user_message: str
    injected_slice: str
    injected_state_tree: str
    tool_calls: list[ToolCallRecord]
    agent_response: str
    checks: list[CheckResult]
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


def build_user_message_with_context(
    user_message: str,
    slice_md: str,
    state_tree: str,
) -> str:
    """构造包含 request_context + business_map_slice + state_tree 的用户消息。"""
    context_parts: list[str] = [
        "[request_context]: current_car: 2021款大众朗逸 1.5L, current_location: (未设置)",
    ]
    if slice_md:
        context_parts.append(f"[business_map_slice]:\n{slice_md}")
    if state_tree:
        context_parts.append(f"[state_tree]:\n{state_tree}")

    context_block: str = "\n\n".join(context_parts)
    return f"{context_block}\n\n{user_message}"


# ============================================================
# 构造故意不完整的切片
# ============================================================


def build_minimal_confirm_saving_slice() -> str:
    """构造一个只包含 confirm_saving 概要但不包含子节点详细内容的切片。

    关键设计：
    - 包含 confirm_saving 的 description 和 checklist
    - 列出 children 引用 (coupon_path, bidding_path) 但只有名称
    - 不包含 coupon_path 和 bidding_path 的 description/checklist/output/cancel_directions
    - 这样模型要回答关于子节点的待办步骤和取消走向，就必须调用 read_business_node
    """
    return textwrap.dedent("""\
        定位深度：2

        ### 养车预订业务地图
        帮助车主完成从需求沟通到预订执行的完整流程。

        ### 沟通项目需求与省钱方案
        本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
        待办：
        - 确认车主的养车项目
        - 了解是否有特殊需求
        - 沟通省钱方法和偏好

        ### 确认省钱方法
        帮助车主选择合适的省钱方式。
        主要有两条路径：优惠券和竞价。
        具体的操作步骤、待办清单和取消规则见子节点定义。
        待办：
        - 介绍可用的省钱方式（需展开子节点查看各路径的具体 checklist）
        - 根据车主偏好推荐方案
        - 确认车主选择
        依赖：
        - 已确认的养车项目（confirm_project 的 output）
        子节点（详细 checklist/output/cancel_directions 未包含在本切片中，需调用 read_business_node 查看）：
        - coupon_path（优惠券路径）
        - bidding_path（竞价路径）

        【注意】本切片仅包含 confirm_saving 层级的概要信息。coupon_path 和 bidding_path 的 checklist、output、cancel_directions 等业务定义未在切片中展开，如需了解需调用 read_business_node("coupon_path") 或 read_business_node("bidding_path")。""")


# ============================================================
# 评估运行器
# ============================================================


async def run_scenario(
    scenario_name: str,
    scenario_desc: str,
    user_message: str,
    slice_md: str,
    state_tree: str,
    checks_fn: Any,
    biz_svc: BusinessMapService,
) -> ScenarioResult:
    """运行单个场景并返回评估结果。"""
    # 追踪工具调用
    tool_calls: list[ToolCallRecord] = []

    # 构建 pydantic_ai Agent
    model: Model = create_model()
    system_prompt: str = build_system_prompt()

    agent: Agent[None, str] = Agent(
        model=model,
        system_prompt=system_prompt,
    )

    # 注册 mock 工具 — update_state_tree
    @agent.tool_plain
    async def update_state_tree(
        content: str,
    ) -> str:
        """更新业务流程状态树到持久化文件。

        状态树格式为缩进 Markdown 清单，每个节点用状态标记：
        - [完成] 已完成的节点，用 → 记录产出
        - [进行中] 正在处理的节点，用 ← 当前 标记焦点
        - [跳过] 已跳过的节点
        - [ ] 尚未开始的节点

        何时调用：
        - 完成一个节点后（标记 [完成] + → 产出）
        - 跳过一个节点后（标记 [跳过]）
        - 开始新节点时（标记 [进行中] + ← 当前）
        - 展开子任务时（从切片中获取 children，添加缩进子项）
        """
        tool_calls.append(ToolCallRecord(
            tool_name="update_state_tree",
            args={"content": content},
            result="状态树已更新",
        ))
        return "状态树已更新"

    # 注册真实工具 — read_business_node（返回 BusinessMapService 的真实数据）
    @agent.tool_plain
    async def read_business_node(
        node_id: str,
    ) -> str:
        """查看指定业务节点的完整业务定义。

        返回该节点的 description、checklist、output、depends_on、cancel_directions 等内容。
        当切片中提到某个节点需要进一步了解、或需要查看某节点的具体 checklist 和取消走向时使用。
        """
        try:
            result: str = biz_svc.get_business_node_detail(node_id)
        except KeyError:
            result = f"节点 '{node_id}' 不存在于业务地图中。"
        tool_calls.append(ToolCallRecord(
            tool_name="read_business_node",
            args={"node_id": node_id},
            result=result,
        ))
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

    # 运行检查
    check_results: list[CheckResult] = checks_fn(tool_calls, agent_response)
    all_passed: bool = all(c.passed for c in check_results)

    return ScenarioResult(
        name=scenario_name,
        description=scenario_desc,
        user_message=user_message,
        injected_slice=slice_md,
        injected_state_tree=state_tree,
        tool_calls=tool_calls,
        agent_response=agent_response,
        checks=check_results,
        passed=all_passed,
        elapsed_seconds=elapsed,
    )


# ============================================================
# 检查函数
# ============================================================


def _checks_s5_read_business_node_required(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """场景 S5：模型必须调用 read_business_node 来获取子节点详情。"""
    checks: list[CheckResult] = []

    # 检查 1：read_business_node 是否被调用
    read_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "read_business_node"
    ]
    has_read: bool = len(read_calls) > 0

    checks.append(CheckResult(
        label="调用了 read_business_node",
        passed=has_read,
        detail=f"调用了 {len(read_calls)} 次, node_ids={[tc.args.get('node_id', '') for tc in read_calls]}"
        if has_read
        else "未调用 read_business_node",
    ))

    # 检查 2：是否查了 coupon_path 或 bidding_path
    target_nodes: set[str] = {"coupon_path", "bidding_path"}
    queried_nodes: set[str] = {
        tc.args.get("node_id", "") for tc in read_calls
    }
    hit_targets: set[str] = target_nodes & queried_nodes
    has_target_read: bool = len(hit_targets) > 0

    checks.append(CheckResult(
        label="查询了 coupon_path 或 bidding_path",
        passed=has_target_read,
        detail=f"命中节点: {hit_targets}" if hit_targets else "未查询目标节点",
    ))

    # 检查 3：回复中包含优惠券或竞价的具体操作内容
    coupon_keywords: list[str] = ["优惠券", "领券", "券", "折扣", "满减", "使用条件"]
    bidding_keywords: list[str] = ["竞价", "比价", "报价", "商户出价", "等待"]
    matched_coupon: list[str] = [kw for kw in coupon_keywords if kw in response]
    matched_bidding: list[str] = [kw for kw in bidding_keywords if kw in response]
    has_detail_content: bool = len(matched_coupon) >= 1 and len(matched_bidding) >= 1

    checks.append(CheckResult(
        label="回复包含优惠券和竞价的具体内容",
        passed=has_detail_content,
        detail=f"优惠券关键词: {matched_coupon}, 竞价关键词: {matched_bidding}",
    ))

    # 检查 4：read_business_node 返回的是真实业务数据
    if read_calls:
        first_result: str = read_calls[0].result
        has_real_data: bool = "checklist" in first_result.lower() or "待办" in first_result or "产出" in first_result
        checks.append(CheckResult(
            label="read_business_node 返回了真实业务数据",
            passed=has_real_data,
            detail=f"返回内容前100字: {first_result[:100]}..." if len(first_result) > 100 else f"返回内容: {first_result}",
        ))
    else:
        checks.append(CheckResult(
            label="read_business_node 返回了真实业务数据",
            passed=False,
            detail="未调用 read_business_node，无法检查返回数据",
        ))

    return checks


# ============================================================
# 场景定义
# ============================================================


def define_scenarios(biz_svc: BusinessMapService) -> list[dict[str, Any]]:
    """定义 S5 评估场景。"""
    # 使用故意不完整的切片
    minimal_slice: str = build_minimal_confirm_saving_slice()

    # 状态树：养车项目已确认，正在进入省钱方法阶段
    state_tree: str = textwrap.dedent("""\
        - [进行中] 沟通项目需求与省钱方案
          - [完成] 确认养车项目 → 小保养（换机油+机滤）
          - [跳过] 确认特殊需求 → 车主无特殊要求
          - [进行中] 确认省钱方法 ← 当前
        - [ ] 筛选匹配商户
        - [ ] 执行预订""")

    scenarios: list[dict[str, Any]] = [
        {
            "name": "S5_read_business_node_required",
            "desc": "切片不包含子节点详情，用户询问具体操作时必须调用 read_business_node",
            "user_message": "优惠券和竞价这两种方式各自要走哪些步骤？如果中途不想用了怎么办？帮我查一下具体的操作流程和取消规则。",
            "slice_md": minimal_slice,
            "state_tree": state_tree,
            "checks_fn": _checks_s5_read_business_node_required,
        },
    ]
    return scenarios


# ============================================================
# 输出格式化
# ============================================================


def format_result(result: ScenarioResult) -> str:
    """格式化单个场景结果为文本。"""
    lines: list[str] = []
    status: str = "PASS" if result.passed else "FAIL"
    lines.append(f"{'=' * 70}")
    lines.append(f"[{status}] {result.name}: {result.description}")
    lines.append(f"{'=' * 70}")
    lines.append(f"用户消息: {result.user_message}")
    lines.append(f"耗时: {result.elapsed_seconds:.1f}s")
    lines.append("")

    # 注入的切片
    lines.append(f"注入切片:\n{result.injected_slice}")
    lines.append("")

    # 注入的状态树
    if result.injected_state_tree:
        lines.append(f"注入状态树:\n{result.injected_state_tree}")
        lines.append("")

    # 工具调用（完整输出，包括 read_business_node 的返回数据）
    if result.tool_calls:
        lines.append(f"工具调用 ({len(result.tool_calls)} 次):")
        for tc in result.tool_calls:
            lines.append(f"  --- {tc.tool_name} ---")
            lines.append(f"  参数: {json.dumps(tc.args, ensure_ascii=False)}")
            # 对于 read_business_node，显示完整返回内容（证明真实数据）
            if tc.tool_name == "read_business_node":
                lines.append(f"  返回数据:\n{textwrap.indent(tc.result, '    ')}")
            else:
                result_preview: str = tc.result[:200] if len(tc.result) > 200 else tc.result
                lines.append(f"  返回: {result_preview}")
        lines.append("")
    else:
        lines.append("工具调用: 无")
        lines.append("")

    # Agent 回复
    lines.append(f"Agent 回复:\n{result.agent_response}")
    lines.append("")

    # 检查结果
    lines.append("检查项:")
    for check in result.checks:
        mark: str = "PASS" if check.passed else "FAIL"
        lines.append(f"  [{mark}] {check.label} — {check.detail}")
    lines.append("")

    return "\n".join(lines)


def format_summary(results: list[ScenarioResult]) -> str:
    """格式化总结。"""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("总结 — read_business_node 路径验证")
    lines.append("=" * 70)

    total: int = len(results)
    passed: int = sum(1 for r in results if r.passed)

    lines.append(f"总场景数: {total}")
    lines.append(f"通过: {passed}")
    lines.append(f"失败: {total - passed}")
    lines.append("")

    for r in results:
        status: str = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.name}: {r.description}")

    lines.append("")

    # 环境信息
    llm_type: str = os.getenv("LLM_TYPE", "unknown")
    deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", os.getenv("LLM_MODEL", "unknown"))
    lines.append(f"模型: {llm_type} / {deployment}")
    lines.append(f"评分方式: read_business_node 调用检查 + 关键词匹配")
    lines.append(f"场景设计: 切片故意不包含子节点详情，迫使模型调用 read_business_node")
    lines.append(f"read_business_node 返回: 来自 BusinessMapService.get_business_node_detail() 的真实数据")
    lines.append("")

    lines.append("验证目标：证明当切片信息不足时，模型会主动调用 read_business_node 获取详情。")

    return "\n".join(lines)


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行 S5 场景并输出结果。"""
    print("read_business_node 路径验证 — Section D Follow-up")
    print("加载业务地图...")

    biz_svc: BusinessMapService = load_business_map()
    print("业务地图加载完成")

    # 验证 read_business_node 能返回真实数据
    print("验证 BusinessMapService.get_business_node_detail 可用...")
    test_detail: str = biz_svc.get_business_node_detail("coupon_path")
    print(f"  coupon_path 详情长度: {len(test_detail)} 字符")
    test_detail2: str = biz_svc.get_business_node_detail("bidding_path")
    print(f"  bidding_path 详情长度: {len(test_detail2)} 字符")
    print("")

    scenarios: list[dict[str, Any]] = define_scenarios(biz_svc)
    print(f"定义了 {len(scenarios)} 个场景")
    print("")

    results: list[ScenarioResult] = []

    for i, scenario in enumerate(scenarios):
        name: str = scenario["name"]
        print(f"运行场景 {i + 1}/{len(scenarios)}: {name} ...")

        result: ScenarioResult = await run_scenario(
            scenario_name=scenario["name"],
            scenario_desc=scenario["desc"],
            user_message=scenario["user_message"],
            slice_md=scenario["slice_md"],
            state_tree=scenario["state_tree"],
            checks_fn=scenario["checks_fn"],
            biz_svc=biz_svc,
        )
        results.append(result)

        status: str = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] 耗时 {result.elapsed_seconds:.1f}s")

    print("")
    print("场景执行完毕，生成报告...")
    print("")

    # 输出详细结果
    output_parts: list[str] = []
    output_parts.append("read_business_node 路径验证报告")
    output_parts.append(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    output_parts.append(f"验证目标: 证明 read_business_node 在信息不足时被模型主动调用")
    output_parts.append("")

    for result in results:
        output_parts.append(format_result(result))

    output_parts.append(format_summary(results))

    full_output: str = "\n".join(output_parts)
    print(full_output)

    # 保存到文件
    output_path: Path = _PROJECT_ROOT / "reports" / "read-business-node-eval-output.txt"
    output_path.write_text(full_output, encoding="utf-8")
    print(f"\n报告已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

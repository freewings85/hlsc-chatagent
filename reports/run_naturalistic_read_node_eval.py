"""自然场景验证：read_business_node 工具路径（无脚手架）。

S6 场景设计要点：
- 注入的切片只包含 confirm_project 节点（含 description / checklist / output / cancel_directions）
- 子节点仅以名称出现在 children 列表中，不展开其 description / checklist / output
- 不提及 read_business_node 工具名，不暗示「需要查看某节点」
- 模型必须独立判断信息不足，自行调用 read_business_node

使用方式：
    export PATH="/home/leo/.local/bin:$PATH"
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    set -a && source mainagent/.env.local && set +a
    uv run python reports/run_naturalistic_read_node_eval.py
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
from typing import Any, Callable

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "mainagent"))
sys.path.insert(0, str(_PROJECT_ROOT / "extensions"))
sys.path.insert(0, str(_PROJECT_ROOT / "sdk"))

from pydantic_ai import Agent
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
# 系统提示词构建
# ============================================================


def load_system_prompt() -> str:
    """加载 SYSTEM.md + SOUL.md + OUTPUT.md + AGENT.md 并拼接。"""
    templates_dir: Path = _PROJECT_ROOT / "mainagent" / "prompts" / "templates"
    parts: list[str] = []
    filename: str
    for filename in ["SYSTEM.md", "SOUL.md", "OUTPUT.md", "AGENT.md"]:
        path: Path = templates_dir / filename
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def build_user_message_with_context(
    user_message: str,
    slice_md: str,
    state_tree: str,
) -> str:
    """构造包含 request_context + business_map_slice + state_tree 的用户消息。

    模拟 HlscContextFormatter 注入逻辑。
    """
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
# 手工切片构建（核心：自然不完整，无脚手架）
# ============================================================


def build_shallow_confirm_project_slice() -> str:
    """构建 confirm_project 的浅层切片。

    只包含 confirm_project 自身的 description / checklist / output / cancel_directions，
    以及子节点列表（仅 id + name + keywords）。
    不展开任何子节点的 description / checklist / output。
    不提及 read_business_node 工具名。
    """
    return textwrap.dedent("""\
        定位深度：2

        ### 养车预订业务地图
        帮助车主完成从需求沟通到预订执行的完整流程。
        project_saving 和 merchant_search 可交叉进行。

        ### 沟通项目需求与省钱方案
        本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
        通常按确认项目 → 特殊需求 → 省钱方法顺序推进。

        ### 确认养车项目
        把车主的表述匹配到具体的养车项目。
        大部分情况能快速通过，不需要过度追问。

        待办：
        - 识别车主描述对应的项目类型
        - 匹配到具体项目
        - 获得车主确认

        产出：
        - 已确认的养车项目名称
        - 项目对应的标准服务内容

        取消走向：
        - 车主不确定要做什么 → 引导到模糊意图场景
        - 车主想先了解价格 → 跳转到确认省钱方法节点

        子节点：
        - direct_expression（直接表达场景）[换机油, 做保养, 换轮胎, 换刹车片]
        - fuzzy_intent（模糊意图场景）[该保养了, 跑了很久, 不知道该做什么]
        - symptom_based（症状描述场景）[异响, 抖动, 故障灯, 漏油]""")


def build_shallow_confirm_saving_slice() -> str:
    """构建 confirm_saving 的浅层切片（备选场景用）。

    只包含 confirm_saving 自身的 description / checklist / output / cancel_directions，
    以及子节点列表（仅 id + name + keywords）。
    不展开 coupon_path 或 bidding_path 的详细内容。
    """
    return textwrap.dedent("""\
        定位深度：2

        ### 养车预订业务地图
        帮助车主完成从需求沟通到预订执行的完整流程。

        ### 沟通项目需求与省钱方案
        本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。

        ### 确认省钱方法
        帮助车主选择合适的省钱方式。
        主要有两条路径：优惠券和竞价。
        可以根据车主偏好推荐，也可以两者结合。
        车主赶时间的话可以简化说明，直接推荐最优方案。

        依赖：
        - 已确认的养车项目（confirm_project 的 output）

        待办：
        - 介绍可用的省钱方式
        - 根据车主偏好推荐方案
        - 确认车主选择

        产出：
        - 车主选择的省钱方式（优惠券/竞价/不需要）
        - 具体的优惠方案明细

        取消走向：
        - 车主不关心省钱 → 标记为不使用省钱方案，继续下一步
        - 车主嫌麻烦 → 推荐最简单的方案或跳过

        子节点：
        - coupon_path（优惠券路径）[优惠券, 券, 折扣, 满减, 领券]
        - bidding_path（竞价路径）[竞价, 比价, 报价, 压价, 商户出价]""")


# ============================================================
# 评估运行器
# ============================================================

# 检查函数签名
ChecksFn = Callable[[list[ToolCallRecord], str], list[CheckResult]]


async def run_scenario(
    scenario_name: str,
    scenario_desc: str,
    user_message: str,
    slice_md: str,
    state_tree: str,
    checks_fn: ChecksFn,
    biz_svc: BusinessMapService,
) -> ScenarioResult:
    """运行单个场景并返回评估结果。"""
    tool_calls: list[ToolCallRecord] = []

    model: Model = create_model()
    system_prompt: str = load_system_prompt()

    agent: Agent[None, str] = Agent(
        model=model,
        system_prompt=system_prompt,
    )

    # 注册工具 — 工具描述与生产一致，不添加额外暗示
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

    full_message: str = build_user_message_with_context(
        user_message, slice_md, state_tree,
    )

    start_time: float = time.time()
    result = await agent.run(full_message)
    elapsed: float = time.time() - start_time

    agent_response: str = result.output

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


def _checks_s6a_fuzzy_intent(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """S6a：模型是否独立调用 read_business_node 获取 fuzzy_intent 节点详情。

    切片中 cancel_directions 提到「引导到模糊意图场景」，
    子节点列表中有 fuzzy_intent，但内容未展开。
    模型应自行判断需要 fuzzy_intent 的 checklist / depends_on 来引导用户。
    """
    checks: list[CheckResult] = []

    # 核心检查：是否调用了 read_business_node
    read_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "read_business_node"
    ]
    has_read: bool = len(read_calls) > 0
    read_node_ids: list[str] = [
        tc.args.get("node_id", "") for tc in read_calls
    ]

    checks.append(CheckResult(
        label="调用了 read_business_node",
        passed=has_read,
        detail=(
            f"调用了 {len(read_calls)} 次, node_ids={read_node_ids}"
            if has_read
            else "未调用 read_business_node"
        ),
    ))

    # 检查是否查了 fuzzy_intent（最合理的目标节点）
    read_fuzzy: bool = "fuzzy_intent" in read_node_ids
    checks.append(CheckResult(
        label="查询了 fuzzy_intent 节点",
        passed=read_fuzzy,
        detail=(
            "正确：查询了 fuzzy_intent"
            if read_fuzzy
            else f"未查 fuzzy_intent，实际查了: {read_node_ids}"
        ),
    ))

    # 辅助检查：回复是否包含了 fuzzy_intent 节点中的信息（里程、保养间隔相关引导）
    guidance_keywords: list[str] = [
        "里程", "保养", "公里", "项目", "推荐", "建议",
        "机油", "小保养", "大保养", "检查",
        "上次", "间隔", "时间",
    ]
    matched: list[str] = [kw for kw in guidance_keywords if kw in response]
    has_guidance: bool = len(matched) >= 2

    checks.append(CheckResult(
        label="回复包含针对模糊意图的引导内容",
        passed=has_guidance,
        detail=(
            f"匹配关键词: {matched}"
            if matched
            else "未匹配到模糊意图引导关键词"
        ),
    ))

    return checks


def _checks_s6b_saving_details(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """S6b：模型是否独立调用 read_business_node 获取 coupon_path 或 bidding_path 详情。

    切片中 confirm_saving 提到两条路径（优惠券/竞价），子节点列表有 coupon_path / bidding_path
    但内容未展开。用户问「省钱方案有哪些选择」时模型应获取详情才能准确回答。
    """
    checks: list[CheckResult] = []

    read_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "read_business_node"
    ]
    has_read: bool = len(read_calls) > 0
    read_node_ids: list[str] = [
        tc.args.get("node_id", "") for tc in read_calls
    ]

    checks.append(CheckResult(
        label="调用了 read_business_node",
        passed=has_read,
        detail=(
            f"调用了 {len(read_calls)} 次, node_ids={read_node_ids}"
            if has_read
            else "未调用 read_business_node"
        ),
    ))

    # 检查是否查了 coupon_path 或 bidding_path
    read_saving_child: bool = (
        "coupon_path" in read_node_ids or "bidding_path" in read_node_ids
    )
    checks.append(CheckResult(
        label="查询了 coupon_path 或 bidding_path 节点",
        passed=read_saving_child,
        detail=(
            f"查询了: {[n for n in read_node_ids if n in ('coupon_path', 'bidding_path')]}"
            if read_saving_child
            else f"未查省钱子节点，实际查了: {read_node_ids}"
        ),
    ))

    # 辅助检查：回复是否区分了两条路径的特点
    path_keywords: list[str] = [
        "优惠券", "券", "折扣", "满减",
        "竞价", "比价", "报价", "商户出价",
    ]
    matched: list[str] = [kw for kw in path_keywords if kw in response]
    has_path_detail: bool = len(matched) >= 2

    checks.append(CheckResult(
        label="回复区分了省钱路径的具体特点",
        passed=has_path_detail,
        detail=(
            f"匹配关键词: {matched}"
            if matched
            else "未匹配到省钱路径关键词"
        ),
    ))

    return checks


# ============================================================
# 场景定义
# ============================================================


def define_scenarios() -> list[dict[str, Any]]:
    """定义 S6 评估场景。"""
    # S6a 状态树：当前在 confirm_project
    state_tree_s6a: str = textwrap.dedent("""\
        - [进行中] 沟通项目需求与省钱方案
          - [进行中] 确认养车项目 ← 当前
          - [ ] 确认特殊需求
          - [ ] 确认省钱方法
        - [ ] 筛选匹配商户
        - [ ] 执行预订""")

    # S6b 状态树：已完成 confirm_project，当前在 confirm_saving
    state_tree_s6b: str = textwrap.dedent("""\
        - [进行中] 沟通项目需求与省钱方案
          - [完成] 确认养车项目 → 小保养（换机油+机滤）
          - [完成] 确认特殊需求 → 无特殊要求
          - [进行中] 确认省钱方法 ← 当前
        - [ ] 筛选匹配商户
        - [ ] 执行预订""")

    scenarios: list[dict[str, Any]] = [
        # ----------------------------------------------------------
        # S6a：模糊意图 — 模型需要自行查看 fuzzy_intent 节点
        # ----------------------------------------------------------
        {
            "name": "S6a_fuzzy_intent_naturalistic",
            "desc": (
                "用户表达模糊意图，切片仅含 confirm_project 浅层信息，"
                "模型应独立调用 read_business_node(fuzzy_intent) 获取引导细节"
            ),
            "user_message": "我不太确定要做什么，车跑了三万多公里，上次保养好像是一万公里前的事了",
            "slice_md": build_shallow_confirm_project_slice(),
            "state_tree": state_tree_s6a,
            "checks_fn": _checks_s6a_fuzzy_intent,
        },
        # ----------------------------------------------------------
        # S6b：省钱详情 — 模型需要自行查看 coupon_path / bidding_path
        # ----------------------------------------------------------
        {
            "name": "S6b_saving_details_naturalistic",
            "desc": (
                "用户想了解省钱方案具体操作，切片仅含 confirm_saving 浅层信息，"
                "模型应独立调用 read_business_node 获取 coupon_path 或 bidding_path 细节"
            ),
            "user_message": "省钱方案有哪些选择？我想了解具体怎么操作",
            "slice_md": build_shallow_confirm_saving_slice(),
            "state_tree": state_tree_s6b,
            "checks_fn": _checks_s6b_saving_details,
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

    # 注入的切片（截断显示）
    if result.injected_slice:
        slice_preview: str = result.injected_slice[:300]
        if len(result.injected_slice) > 300:
            slice_preview += "..."
        lines.append(f"注入切片（前300字）:\n{slice_preview}")
        lines.append("")

    # 注入的状态树
    if result.injected_state_tree:
        lines.append(f"注入状态树:\n{result.injected_state_tree}")
        lines.append("")

    # 工具调用
    if result.tool_calls:
        lines.append(f"工具调用 ({len(result.tool_calls)} 次):")
        tc: ToolCallRecord
        for tc in result.tool_calls:
            args_display: dict[str, Any] = {}
            k: str
            v: Any
            for k, v in tc.args.items():
                if isinstance(v, str) and len(v) > 200:
                    args_display[k] = v[:200] + "..."
                else:
                    args_display[k] = v
            lines.append(
                f"  - {tc.tool_name}({json.dumps(args_display, ensure_ascii=False)})"
            )
        lines.append("")
    else:
        lines.append("工具调用: 无")
        lines.append("")

    # Agent 回复
    lines.append(f"Agent 回复:\n{result.agent_response}")
    lines.append("")

    # 检查项
    lines.append("检查项:")
    check: CheckResult
    for check in result.checks:
        mark: str = "PASS" if check.passed else "FAIL"
        lines.append(f"  [{mark}] {check.label} — {check.detail}")
    lines.append("")

    return "\n".join(lines)


def format_summary(results: list[ScenarioResult]) -> str:
    """格式化总结。"""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("总结")
    lines.append("=" * 70)

    total: int = len(results)
    passed: int = sum(1 for r in results if r.passed)
    failed: int = total - passed

    lines.append(f"总场景数: {total}")
    lines.append(f"通过: {passed}")
    lines.append(f"失败: {failed}")
    lines.append("")

    r: ScenarioResult
    for r in results:
        status: str = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.name}: {r.description}")

    lines.append("")

    # 环境信息
    llm_type: str = os.getenv("LLM_TYPE", "unknown")
    deployment: str = os.getenv(
        "AZURE_DEPLOYMENT_NAME", os.getenv("LLM_MODEL", "unknown"),
    )
    lines.append(f"模型: {llm_type} / {deployment}")
    lines.append("评分方式: 工具调用检查 + 关键词匹配")
    lines.append("通过阈值: 全部检查项通过")
    lines.append("")
    lines.append("设计说明:")
    lines.append("  - 切片中不提及 read_business_node 工具名")
    lines.append("  - 切片中不暗示「需要查看某节点」")
    lines.append("  - 子节点仅以 id + name 列出，不展开详细内容")
    lines.append("  - 模型必须独立判断信息不足并自行调用工具")

    return "\n".join(lines)


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行 S6 自然场景评估。"""
    print("自然场景 read_business_node 验证 — S6")
    print("加载业务地图...")

    biz_svc: BusinessMapService = load_business_map()
    print("业务地图加载完成")

    scenarios: list[dict[str, Any]] = define_scenarios()
    print(f"定义了 {len(scenarios)} 个场景")
    print("")

    results: list[ScenarioResult] = []

    i: int
    scenario: dict[str, Any]
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
    print("所有场景执行完毕，生成报告...")
    print("")

    # 输出详细结果
    output_parts: list[str] = []
    output_parts.append("自然场景 read_business_node 验证报告 — S6")
    output_parts.append(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    output_parts.append("")

    result_item: ScenarioResult
    for result_item in results:
        output_parts.append(format_result(result_item))

    output_parts.append(format_summary(results))

    full_output: str = "\n".join(output_parts)
    print(full_output)

    # 保存到文件
    output_path: Path = _PROJECT_ROOT / "reports" / "naturalistic-read-node-eval-output.txt"
    output_path.write_text(full_output, encoding="utf-8")
    print(f"\n报告已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

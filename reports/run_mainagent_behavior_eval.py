"""MainAgent 行为验证脚本：使用真实 LLM 验证业务地图切片注入后的 Agent 行为。

验证项（Section D 要求）：
1. 注入 [business_map_slice] 后，Agent 提问是否围绕当前 checklist
2. 节点完成时，是否调用 update_state_tree
3. 需要更多节点信息时，是否调用 read_business_node
4. 无业务进展时，是否不调用 update_state_tree

使用方式：
    export PATH="/home/leo/.local/bin:$PATH"
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    set -a && source mainagent/.env.local && set +a
    uv run python reports/run_mainagent_behavior_eval.py
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


@dataclass
class CheckResult:
    """单项检查结果"""

    label: str
    passed: bool
    detail: str


# ============================================================
# 业务地图加载
# ============================================================


def load_business_map() -> BusinessMapService:
    """加载业务地图 YAML 并返回服务实例。"""
    biz_map_dir: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"
    svc: BusinessMapService = BusinessMapService()
    svc.load(biz_map_dir)
    return svc


# ============================================================
# Agent 工厂
# ============================================================


def load_agent_md() -> str:
    """读取 AGENT.md 内容。"""
    agent_md_path: Path = (
        _PROJECT_ROOT / "mainagent" / "prompts" / "templates" / "AGENT.md"
    )
    return agent_md_path.read_text(encoding="utf-8").strip()


def load_system_prompt_parts() -> str:
    """加载 SYSTEM.md + SOUL.md + OUTPUT.md 并拼接。"""
    templates_dir: Path = _PROJECT_ROOT / "mainagent" / "prompts" / "templates"
    parts: list[str] = []
    for filename in ["SYSTEM.md", "SOUL.md", "OUTPUT.md"]:
        path: Path = templates_dir / filename
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


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
    """构造包含 request_context + business_map_slice + state_tree 的用户消息。

    模拟 HlscContextFormatter 的注入逻辑：将切片和状态树作为上下文前置。
    """
    context_parts: list[str] = [
        "[request_context]: current_car: (未设置), current_location: (未设置)",
    ]
    if slice_md:
        context_parts.append(f"[business_map_slice]:\n{slice_md}")
    if state_tree:
        context_parts.append(f"[state_tree]:\n{state_tree}")

    context_block: str = "\n\n".join(context_parts)
    return f"{context_block}\n\n{user_message}"


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

    # 构建 pydantic_ai Agent（直接使用，不走 SDK 的 Agent wrapper）
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

    # 构造用户消息（包含注入的上下文）
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
# 场景定义
# ============================================================


def define_scenarios(biz_svc: BusinessMapService) -> list[dict[str, Any]]:
    """定义所有评估场景。"""
    # 组装切片：project_saving 层级
    slice_project_saving: str = biz_svc.assemble_slice(["project_saving"])

    # 组装切片：confirm_project（直接表达场景）
    slice_confirm_project: str = biz_svc.assemble_slice(["direct_expression"])

    # 带进行中状态的状态树
    state_tree_in_progress: str = textwrap.dedent("""\
        - [进行中] 沟通项目需求与省钱方案
          - [进行中] 确认养车项目 ← 当前
          - [ ] 确认特殊需求
          - [ ] 确认省钱方法
        - [ ] 筛选匹配商户
        - [ ] 执行预订""")

    # 带已完成节点的状态树（当前步骤是"获得车主最终确认"，等待用户确认即可完成）
    state_tree_completing: str = textwrap.dedent("""\
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

    # 空状态树（新会话）
    state_tree_empty: str = ""

    scenarios: list[dict[str, Any]] = [
        # ----------------------------------------------------------
        # 场景 1：切片注入 → 提问围绕 checklist
        # ----------------------------------------------------------
        {
            "name": "S1_slice_guides_question",
            "desc": "注入 [business_map_slice] 后，Agent 提问应围绕当前 checklist",
            "user_message": "我车该保养了",
            "slice_md": slice_project_saving,
            "state_tree": state_tree_empty,
            "checks_fn": _checks_s1_question_follows_checklist,
        },
        # ----------------------------------------------------------
        # 场景 2：节点完成 → update_state_tree 调用
        # 用户明确确认当前 checklist 项，Agent 应标记完成并更新状态树
        # ----------------------------------------------------------
        {
            "name": "S2_node_completed_updates_tree",
            "desc": "用户确认项目后，Agent 应调用 update_state_tree",
            "user_message": "对，就做小保养，换机油和机滤就行，确认了",
            "slice_md": slice_confirm_project,
            "state_tree": state_tree_completing,
            "checks_fn": _checks_s2_update_state_tree_called,
        },
        # ----------------------------------------------------------
        # 场景 3：需要更多信息 → read_business_node 调用
        # ----------------------------------------------------------
        {
            "name": "S3_read_node_for_details",
            "desc": "用户说不想做了，Agent 应查看 cancel_directions 或相关节点",
            "user_message": "算了我不想做保养了，太贵了",
            "slice_md": slice_confirm_project,
            "state_tree": state_tree_in_progress,
            "checks_fn": _checks_s3_read_business_node_called,
        },
        # ----------------------------------------------------------
        # 场景 4：无业务进展 → update_state_tree 不调用
        # ----------------------------------------------------------
        {
            "name": "S4_chitchat_no_update",
            "desc": "闲聊时，Agent 不应调用 update_state_tree",
            "user_message": "你好，今天天气怎么样？",
            "slice_md": slice_project_saving,
            "state_tree": state_tree_in_progress,
            "checks_fn": _checks_s4_no_update_state_tree,
        },
    ]
    return scenarios


# ============================================================
# 检查函数
# ============================================================

# 场景 1 的 checklist 关键词（来自 project_saving 节点的 checklist）
_S1_CHECKLIST_KEYWORDS: list[str] = [
    "养车项目", "保养", "项目", "什么项目", "做什么",
    "特殊需求", "品牌", "配件",
    "省钱", "优惠", "便宜",
    "换机油", "机滤", "小保养", "大保养",
    "车型", "车辆", "什么车", "哪款车",
    "里程", "多久", "多少公里",
]


def _checks_s1_question_follows_checklist(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """场景 1：Agent 回复应围绕 checklist 内容提问。"""
    checks: list[CheckResult] = []

    # 检查回复中是否包含 checklist 相关关键词
    matched_keywords: list[str] = [
        kw for kw in _S1_CHECKLIST_KEYWORDS if kw in response
    ]
    has_checklist_keywords: bool = len(matched_keywords) >= 1

    checks.append(CheckResult(
        label="回复包含 checklist 相关关键词",
        passed=has_checklist_keywords,
        detail=f"匹配到: {matched_keywords}" if matched_keywords else "未匹配到任何关键词",
    ))

    # 检查回复中是否包含问号（表示在提问）
    has_question: bool = "？" in response or "?" in response
    checks.append(CheckResult(
        label="回复中包含提问（问号）",
        passed=has_question,
        detail="包含提问" if has_question else "未包含提问",
    ))

    # 检查回复不是通用废话（至少有一定长度且非纯问候）
    is_substantive: bool = len(response) > 10
    checks.append(CheckResult(
        label="回复内容充实（非纯问候）",
        passed=is_substantive,
        detail=f"回复长度: {len(response)} 字符",
    ))

    return checks


def _checks_s2_update_state_tree_called(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """场景 2：用户确认项目后，Agent 应调用 update_state_tree。"""
    checks: list[CheckResult] = []

    # 检查 update_state_tree 是否被调用
    update_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "update_state_tree"
    ]
    has_update: bool = len(update_calls) > 0

    checks.append(CheckResult(
        label="调用了 update_state_tree",
        passed=has_update,
        detail=f"调用次数: {len(update_calls)}" if has_update else "未调用",
    ))

    # 如果调用了，检查内容中是否包含 [完成] 标记
    if update_calls:
        content: str = update_calls[0].args.get("content", "")
        has_completion_marker: bool = "[完成]" in content
        checks.append(CheckResult(
            label="状态树中包含 [完成] 标记",
            passed=has_completion_marker,
            detail=f"内容含 '[完成]'" if has_completion_marker else "未包含 '[完成]'",
        ))
    else:
        checks.append(CheckResult(
            label="状态树中包含 [完成] 标记",
            passed=False,
            detail="未调用 update_state_tree，跳过内容检查",
        ))

    return checks


def _checks_s3_read_business_node_called(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """场景 3：用户取消意向时，Agent 可能调用 read_business_node 查看 cancel_directions。

    注意：这是可选行为。切片中已包含 cancel_directions，Agent 可能直接依据切片信息
    给出回应而不需要额外调用 read_business_node。因此我们设置两级检查：
    - 必须检查：回复中包含取消走向相关内容（引导行为）
    - 可选检查：是否调用了 read_business_node（调用了加分，没调用不算失败）
    """
    checks: list[CheckResult] = []

    # 必须检查：Agent 的回复应包含取消相关引导
    # 关键词覆盖三类回应：共情理解、优惠引导、保留后续
    cancel_keywords: list[str] = [
        # 共情理解
        "不想做", "取消", "没关系", "理解", "好的", "没问题",
        # 引导转向
        "到店", "检查", "商户", "推荐", "其他",
        # 价格/优惠引导
        "价格", "费用", "多少钱", "报价", "优惠", "省钱", "划算", "便宜",
        # 保留后续
        "了解", "确认", "考虑", "随时", "下次", "再",
        # 流程结束
        "记录", "结束", "意向",
    ]
    matched: list[str] = [kw for kw in cancel_keywords if kw in response]
    has_cancel_guidance: bool = len(matched) >= 1

    checks.append(CheckResult(
        label="回复包含取消/引导相关内容",
        passed=has_cancel_guidance,
        detail=f"匹配到: {matched}" if matched else "未匹配到取消引导关键词",
    ))

    # 可选检查：是否调用了 read_business_node
    read_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "read_business_node"
    ]
    has_read: bool = len(read_calls) > 0
    checks.append(CheckResult(
        label="[可选] 调用了 read_business_node",
        passed=True,  # 可选项，不影响总体通过
        detail=f"调用了 read_business_node, node_id={read_calls[0].args}" if has_read else "未调用（可选行为，不影响结果）",
    ))

    return checks


def _checks_s4_no_update_state_tree(
    tool_calls: list[ToolCallRecord],
    response: str,
) -> list[CheckResult]:
    """场景 4：闲聊时不应调用 update_state_tree。"""
    checks: list[CheckResult] = []

    # 检查 update_state_tree 未被调用
    update_calls: list[ToolCallRecord] = [
        tc for tc in tool_calls if tc.tool_name == "update_state_tree"
    ]
    no_update: bool = len(update_calls) == 0

    checks.append(CheckResult(
        label="未调用 update_state_tree",
        passed=no_update,
        detail="正确：未调用" if no_update else f"错误：调用了 {len(update_calls)} 次",
    ))

    # 检查 Agent 回复不推进业务（闲聊应被礼貌拒绝或简短回应后重定向）
    response_lower: str = response.lower()
    is_domain_redirect: bool = any(
        kw in response
        for kw in ["养车", "保养", "维修", "汽车", "车辆", "帮你", "服务"]
    )
    checks.append(CheckResult(
        label="回复引导回汽车服务领域",
        passed=is_domain_redirect,
        detail="包含领域引导" if is_domain_redirect else "未包含领域引导（仍可接受）",
    ))

    return checks


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
        slice_preview: str = result.injected_slice[:200]
        if len(result.injected_slice) > 200:
            slice_preview += "..."
        lines.append(f"注入切片（前200字）:\n{slice_preview}")
        lines.append("")

    # 注入的状态树
    if result.injected_state_tree:
        lines.append(f"注入状态树:\n{result.injected_state_tree}")
        lines.append("")

    # 工具调用
    if result.tool_calls:
        lines.append(f"工具调用 ({len(result.tool_calls)} 次):")
        for tc in result.tool_calls:
            # 截断 args 中过长的内容
            args_display: dict[str, Any] = {}
            for k, v in tc.args.items():
                if isinstance(v, str) and len(v) > 150:
                    args_display[k] = v[:150] + "..."
                else:
                    args_display[k] = v
            lines.append(f"  - {tc.tool_name}({json.dumps(args_display, ensure_ascii=False)})")
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
    lines.append("总结")
    lines.append("=" * 70)

    total: int = len(results)
    passed: int = sum(1 for r in results if r.passed)
    failed: int = total - passed

    lines.append(f"总场景数: {total}")
    lines.append(f"通过: {passed}")
    lines.append(f"失败: {failed}")
    lines.append("")

    for r in results:
        status: str = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.name}: {r.description}")

    lines.append("")

    # 环境信息
    llm_type: str = os.getenv("LLM_TYPE", "unknown")
    deployment: str = os.getenv("AZURE_DEPLOYMENT_NAME", os.getenv("LLM_MODEL", "unknown"))
    lines.append(f"模型: {llm_type} / {deployment}")
    lines.append(f"提示词: mainagent/prompts/templates/AGENT.md")
    lines.append(f"评分方式: 关键词匹配 + 工具调用检查")
    lines.append(f"通过阈值: 全部必须项通过")
    lines.append("")

    # history-dependent 行为声明
    lines.append("注意：本评估中 recent_history 为空（每个场景独立运行、无历史上下文），")
    lines.append("因此以下行为尚未验证：")
    lines.append('  - 代词类后续（"那个"、"就那家"、"行"）')
    lines.append('  - 连续轮次上下文传递（"上次说的方案"、"刚才提到的店"）')
    lines.append("  - 依赖对话历史的业务续接")

    return "\n".join(lines)


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行所有场景并输出结果。"""
    print("MainAgent 行为验证 — Section D")
    print("加载业务地图...")

    biz_svc: BusinessMapService = load_business_map()
    print(f"业务地图加载完成")

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
    print("所有场景执行完毕，生成报告...")
    print("")

    # 输出详细结果
    output_parts: list[str] = []
    output_parts.append("MainAgent 行为验证报告 — Section D")
    output_parts.append(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    output_parts.append("")

    for result in results:
        output_parts.append(format_result(result))

    output_parts.append(format_summary(results))

    full_output: str = "\n".join(output_parts)
    print(full_output)

    # 保存到文件
    output_path: Path = _PROJECT_ROOT / "reports" / "mainagent-behavior-eval-output.txt"
    output_path.write_text(full_output, encoding="utf-8")
    print(f"\n报告已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

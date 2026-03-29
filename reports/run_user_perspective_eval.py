"""用户视角 Navigator 评估脚本。

从真实车主行为习惯出发，评估 BusinessMapAgent 导航定位器的表现。
额外跟踪格式合规率、按类别细分、失败原因分析和改进建议。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── 路径注入 ──
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "subagents" / "business_map_agent"))
sys.path.insert(0, str(_PROJECT_ROOT / "extensions"))
sys.path.insert(0, str(_PROJECT_ROOT / "sdk"))

from agent_sdk._agent.model import create_model  # noqa: E402
from hlsc.services.business_map_service import BusinessMapService  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models import Model  # noqa: E402

# ── 常量 ──
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"
_SYSTEM_PROMPT_PATH: Path = (
    _PROJECT_ROOT / "subagents" / "business_map_agent" / "prompts" / "templates" / "system.md"
)
_DATASET_PATH: Path = _PROJECT_ROOT / "reports" / "user-perspective-eval-dataset.jsonl"
_RESULTS_PATH: Path = _PROJECT_ROOT / "reports" / "user-perspective-eval-results.jsonl"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
logger: logging.Logger = logging.getLogger("user_perspective_eval")
logger.setLevel(logging.INFO)

# ── 业务地图中所有有效的节点 ID ──
VALID_NODE_IDS: set[str] = {
    "root", "project_saving", "confirm_project", "direct_expression",
    "fuzzy_intent", "symptom_based", "confirm_requirements", "confirm_saving",
    "coupon_path", "bidding_path", "merchant_search", "search", "compare",
    "confirm", "booking", "build_plan", "execute",
}


# ── 数据模型 ──


@dataclass
class EvalSample:
    """评估数据集的一条样本。"""

    id: str
    category: str
    subcategory: str
    user_message: str
    state_briefing: str
    expected_ids: list[str]
    acceptable_ancestors: list[str]
    unacceptable_over_deep: list[str]
    rationale: str


# 格式合规分类
FORMAT_STRICT: str = "strict"       # 输出仅包含节点 ID，无多余内容
FORMAT_RECOVERED: str = "recovered"  # 输出包含额外内容但能解析出正确 ID
FORMAT_INVALID: str = "hard_invalid"  # 无法解析出任何有效 ID


# 失败原因类型
FAIL_FORMAT: str = "FORMAT"           # 输出格式问题（JSON 回显等）
FAIL_SHALLOW: str = "SHALLOW"         # 停得太浅
FAIL_WRONG_BRANCH: str = "WRONG_BRANCH"  # 走错分支
FAIL_NO_STATE_USE: str = "NO_STATE_USE"  # 忽略状态简报
FAIL_OVER_DEEP: str = "OVER_DEEP"     # 过度下钻
FAIL_OTHER: str = "OTHER"             # 其他


@dataclass
class EvalResult:
    """一条样本的评估结果。"""

    id: str
    category: str
    subcategory: str
    user_message: str
    expected_ids: list[str]
    actual_ids: list[str]
    raw_output: str
    exact_match: bool
    ancestor_match: bool
    over_deep: bool
    format_compliance: str  # strict / recovered / hard_invalid
    fail_reason: str  # 失败原因分类（仅 MISS 时填写）
    fail_detail: str  # 失败具体描述
    error: str = ""


@dataclass
class CategoryStats:
    """单个类别的统计数据。"""

    total: int = 0
    exact: int = 0
    ancestor: int = 0
    over_deep: int = 0
    error: int = 0


@dataclass
class EvalSummary:
    """评估汇总指标。"""

    total: int = 0
    exact_match_count: int = 0
    ancestor_match_count: int = 0
    over_deep_count: int = 0
    error_count: int = 0
    # 格式合规统计
    format_strict_count: int = 0
    format_recovered_count: int = 0
    format_invalid_count: int = 0
    # 按类别（含子类别）统计
    category_stats: dict[str, CategoryStats] = field(default_factory=dict)
    # 失败原因统计
    fail_reasons: Counter[str] = field(default_factory=Counter)
    # 失败案例详情
    failures: list[EvalResult] = field(default_factory=list)


# ── 祖先映射 ──


def _build_ancestor_map() -> dict[str, list[str]]:
    """构建每个节点到其所有祖先 ID 的映射。"""
    tree: dict[str, list[str]] = {
        "root": [],
        "project_saving": ["root"],
        "confirm_project": ["root", "project_saving"],
        "direct_expression": ["root", "project_saving", "confirm_project"],
        "fuzzy_intent": ["root", "project_saving", "confirm_project"],
        "symptom_based": ["root", "project_saving", "confirm_project"],
        "confirm_requirements": ["root", "project_saving"],
        "confirm_saving": ["root", "project_saving"],
        "coupon_path": ["root", "project_saving", "confirm_saving"],
        "bidding_path": ["root", "project_saving", "confirm_saving"],
        "merchant_search": ["root"],
        "search": ["root", "merchant_search"],
        "compare": ["root", "merchant_search"],
        "confirm": ["root", "merchant_search"],
        "booking": ["root"],
        "build_plan": ["root", "booking"],
        "execute": ["root", "booking"],
    }
    return tree


ANCESTOR_MAP: dict[str, list[str]] = _build_ancestor_map()


# ── 后代映射（用于判断 SHALLOW） ──


def _build_descendant_map() -> dict[str, set[str]]:
    """构建每个节点到其所有后代 ID 的映射。"""
    descendants: dict[str, set[str]] = {nid: set() for nid in VALID_NODE_IDS}
    node_id: str
    ancestors: list[str]
    for node_id, ancestors in ANCESTOR_MAP.items():
        ancestor: str
        for ancestor in ancestors:
            descendants[ancestor].add(node_id)
    return descendants


DESCENDANT_MAP: dict[str, set[str]] = _build_descendant_map()


# ── 业务地图工具函数 ──


def create_tool_functions(service: BusinessMapService) -> list[Any]:
    """创建纯函数版工具（pydantic_ai.Agent 原生格式）。"""

    def get_business_children(node_id: str = "root") -> str:
        """获取指定业务节点的子节点列表（id、name、keywords），用于导航决策。首次调用传 node_id='root' 从根节点开始。"""
        try:
            result: str = service.get_business_children_nav(node_id)
            return result
        except KeyError:
            return f"节点 '{node_id}' 不存在。请检查 node_id 是否正确。"

    def get_business_node(node_id: str) -> str:
        """获取单个业务节点的导航详情（id、name、keywords、是否有子节点）。当需要确认某个节点是否为叶节点时使用。"""
        try:
            result: str = service.get_business_node_nav(node_id)
            return result
        except KeyError:
            return f"节点 '{node_id}' 不存在。请检查 node_id 是否正确。"

    return [get_business_children, get_business_node]


# ── 输出解析与格式合规检测 ──


def classify_format(raw_output: str) -> str:
    """判断输出的格式合规等级。

    - strict: 输出仅包含逗号分隔的节点 ID（可能带空格），无其他内容
    - recovered: 包含额外内容（解释、JSON 等）但能从中提取出有效 ID
    - hard_invalid: 无法提取任何有效 ID
    """
    cleaned: str = raw_output.strip()

    if not cleaned:
        return FORMAT_INVALID

    # 严格模式：仅包含逗号分隔的有效节点 ID
    # 允许 "node_id" 或 "node_id, node_id2" 格式
    candidates: list[str] = [c.strip() for c in cleaned.split(",")]
    if all(c in VALID_NODE_IDS for c in candidates if c):
        return FORMAT_STRICT

    # 检查是否包含多行或额外内容
    lines: list[str] = [l.strip() for l in cleaned.split("\n") if l.strip()]

    # 如果只有一行，但包含非 ID 字符
    if len(lines) == 1:
        # 去掉所有合法 ID 和分隔符后看是否有残留
        remaining: str = cleaned
        for nid in sorted(VALID_NODE_IDS, key=len, reverse=True):
            remaining = remaining.replace(nid, "")
        remaining = remaining.replace(",", "").replace(" ", "").strip()
        if not remaining:
            return FORMAT_STRICT

    # 尝试从中提取 ID
    extracted: list[str] = parse_node_ids(raw_output)
    if extracted:
        return FORMAT_RECOVERED

    return FORMAT_INVALID


def parse_node_ids(raw_output: str) -> list[str]:
    """从模型原始输出中解析节点 ID 列表。

    处理多种输出格式：
    - 纯 ID：project_saving
    - 逗号分隔：confirm_saving, search
    - JSON 混合：{"node_id":"root"}\\nproject_saving
    - 多行混合输出
    """
    cleaned: str = raw_output.strip()

    # 去掉 markdown code block
    if cleaned.startswith("```"):
        lines: list[str] = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    # 策略1：尝试从输出的最后一行提取
    output_lines: list[str] = [
        line.strip() for line in cleaned.split("\n") if line.strip()
    ]

    # 策略2：提取所有出现的有效 node_id
    all_found_ids: list[str] = []
    node_id: str
    for node_id in VALID_NODE_IDS:
        pattern: str = r'\b' + re.escape(node_id) + r'\b'
        if re.search(pattern, cleaned):
            all_found_ids.append(node_id)

    # 策略3：如果最后一行是纯 ID 格式，优先使用
    if output_lines:
        last_line: str = output_lines[-1]
        if not last_line.startswith("{") and not last_line.startswith("["):
            last_line_ids: list[str] = []
            candidate: str
            for candidate in re.split(r'[,\s]+', last_line):
                candidate = candidate.strip()
                if candidate in VALID_NODE_IDS:
                    last_line_ids.append(candidate)
            if last_line_ids:
                return last_line_ids

    # 策略4：非 JSON 行中的 ID
    non_json_ids: list[str] = []
    line: str
    for line in output_lines:
        stripped: str = line.strip()
        if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("}") or stripped.startswith("]"):
            continue
        if len(stripped) > 50 and any(c in stripped for c in "。，？！（）"):
            continue
        for nid in VALID_NODE_IDS:
            pattern_str: str = r'\b' + re.escape(nid) + r'\b'
            if re.search(pattern_str, stripped):
                if nid not in non_json_ids:
                    non_json_ids.append(nid)

    if non_json_ids:
        return non_json_ids

    # 策略5：fallback，过滤祖先关系只保留最深
    if all_found_ids:
        filtered: list[str] = []
        fid: str
        for fid in all_found_ids:
            is_ancestor_of_another: bool = any(
                fid in ANCESTOR_MAP.get(other_id, [])
                for other_id in all_found_ids
                if other_id != fid
            )
            if not is_ancestor_of_another:
                filtered.append(fid)

        root_children: set[str] = {"project_saving", "merchant_search", "booking"}
        if root_children.issubset(set(filtered)):
            return []

        return filtered if filtered else all_found_ids

    return []


# ── 失败原因诊断 ──


def diagnose_failure(
    sample: EvalSample,
    actual_ids: list[str],
    raw_output: str,
    format_compliance: str,
) -> tuple[str, str]:
    """诊断失败原因，返回 (原因分类, 具体描述)。"""
    expected_set: set[str] = set(sample.expected_ids)
    actual_set: set[str] = set(actual_ids)

    # 1. 格式问题：无法解析出任何 ID
    if format_compliance == FORMAT_INVALID or not actual_ids:
        return FAIL_FORMAT, f"输出无法解析为有效节点 ID: {raw_output[:100]}"

    # 2. 过度下钻：actual 包含 unacceptable_over_deep 中的节点
    if actual_set & set(sample.unacceptable_over_deep):
        over_deep_nodes: set[str] = actual_set & set(sample.unacceptable_over_deep)
        return FAIL_OVER_DEEP, f"过度下钻到 {over_deep_nodes}，期望停在 {expected_set}"

    # 3. 检查是否停得太浅（actual 是 expected 的祖先）
    is_shallow: bool = False
    aid: str
    for aid in actual_ids:
        eid: str
        for eid in sample.expected_ids:
            if aid in ANCESTOR_MAP.get(eid, []):
                is_shallow = True
                break

    if is_shallow and not (actual_set & expected_set):
        return FAIL_SHALLOW, f"停在 {actual_ids}，期望深入到 {sample.expected_ids}"

    # 4. 忽略状态简报（有状态但 actual 与无状态时的结果一样）
    if sample.state_briefing:
        # 如果有状态简报但结果明显没考虑状态
        # 例如：状态说 confirm_project 已完成，但还是定位到 confirm_project
        completed_nodes: list[str] = []
        for part in sample.state_briefing.split("\n"):
            part = part.strip()
            for nid in VALID_NODE_IDS:
                if nid in part and ("完成" in part or "已完成" in part):
                    completed_nodes.append(nid)

        if any(aid in completed_nodes for aid in actual_ids):
            return FAIL_NO_STATE_USE, f"定位到已完成的节点 {actual_ids}，状态简报被忽略"

    # 5. 走错分支
    # 检查 actual 和 expected 是否在不同的顶层分支
    def get_top_branch(nid: str) -> str:
        """获取节点所属的顶层分支。"""
        ancestors: list[str] = ANCESTOR_MAP.get(nid, [])
        if "project_saving" in ancestors or nid == "project_saving":
            return "project_saving"
        if "merchant_search" in ancestors or nid == "merchant_search":
            return "merchant_search"
        if "booking" in ancestors or nid == "booking":
            return "booking"
        return nid

    expected_branches: set[str] = {get_top_branch(eid) for eid in sample.expected_ids}
    actual_branches: set[str] = {get_top_branch(aid) for aid in actual_ids}

    if not (expected_branches & actual_branches) and actual_ids:
        return FAIL_WRONG_BRANCH, f"走到 {actual_branches} 分支，期望在 {expected_branches} 分支"

    # 6. 其他
    return FAIL_OTHER, f"actual={actual_ids}, expected={sample.expected_ids}"


# ── 评分逻辑 ──


def score_sample(
    sample: EvalSample,
    actual_ids: list[str],
    raw_output: str,
) -> EvalResult:
    """对单条样本评分。"""
    expected_set: set[str] = set(sample.expected_ids)
    actual_set: set[str] = set(actual_ids)

    # exact_match: 完全一致
    exact_match: bool = expected_set == actual_set

    # ancestor_match: actual 中的 ID 都在可接受范围内
    ancestor_match: bool = False
    if not exact_match and actual_ids:
        acceptable_set: set[str] = set(sample.acceptable_ancestors) | expected_set
        ancestor_match = all(aid in acceptable_set for aid in actual_ids)

    # over_deep: actual 中包含不可接受的过深节点
    over_deep: bool = bool(actual_set & set(sample.unacceptable_over_deep))

    # 格式合规
    format_compliance: str = classify_format(raw_output)

    # 失败原因
    fail_reason: str = ""
    fail_detail: str = ""
    if not exact_match and not ancestor_match:
        fail_reason, fail_detail = diagnose_failure(
            sample, actual_ids, raw_output, format_compliance
        )

    return EvalResult(
        id=sample.id,
        category=sample.category,
        subcategory=sample.subcategory,
        user_message=sample.user_message,
        expected_ids=sample.expected_ids,
        actual_ids=actual_ids,
        raw_output="",  # 在调用处填充
        exact_match=exact_match,
        ancestor_match=ancestor_match,
        over_deep=over_deep,
        format_compliance=format_compliance,
        fail_reason=fail_reason,
        fail_detail=fail_detail,
    )


# ── 主执行逻辑 ──


def load_dataset(path: Path) -> list[EvalSample]:
    """加载 JSONL 数据集。"""
    samples: list[EvalSample] = []
    with open(path, "r", encoding="utf-8") as f:
        line: str
        for line in f:
            line = line.strip()
            if not line:
                continue
            data: dict[str, Any] = json.loads(line)
            samples.append(
                EvalSample(
                    id=data["id"],
                    category=data["category"],
                    subcategory=data.get("subcategory", ""),
                    user_message=data["user_message"],
                    state_briefing=data.get("state_briefing", ""),
                    expected_ids=data["expected_ids"],
                    acceptable_ancestors=data.get("acceptable_ancestors", []),
                    unacceptable_over_deep=data.get("unacceptable_over_deep", []),
                    rationale=data.get("rationale", ""),
                )
            )
    return samples


def build_user_prompt(sample: EvalSample) -> str:
    """构建发送给 Agent 的用户消息。

    如果有 state_briefing，将其作为上下文前缀。
    """
    parts: list[str] = []
    if sample.state_briefing:
        parts.append(f"[状态简报] {sample.state_briefing}")
    parts.append(sample.user_message)
    return "\n".join(parts)


async def run_single(
    agent: Agent[None, str],
    sample: EvalSample,
    index: int,
    total: int,
) -> EvalResult:
    """运行单条评估样本。"""
    user_prompt: str = build_user_prompt(sample)
    logger.info(
        "[%d/%d] %s (%s) | 用户消息: %s",
        index, total, sample.id, sample.category, sample.user_message[:50],
    )

    raw_output: str = ""
    actual_ids: list[str] = []
    error: str = ""

    try:
        result = await agent.run(user_prompt)
        raw_output = result.output if isinstance(result.output, str) else str(result.output)
        actual_ids = parse_node_ids(raw_output)
        logger.info(
            "  -> 输出: %s | 解析: %s | 期望: %s",
            raw_output.strip()[:80],
            actual_ids,
            sample.expected_ids,
        )
    except Exception as e:
        error = str(e)
        logger.error("  -> 错误: %s", error[:200])

    eval_result: EvalResult = score_sample(sample, actual_ids, raw_output)
    eval_result.raw_output = raw_output
    eval_result.error = error

    # 如果有错误，覆盖格式合规为 invalid
    if error:
        eval_result.format_compliance = FORMAT_INVALID
        eval_result.fail_reason = FAIL_FORMAT
        eval_result.fail_detail = f"运行错误: {error[:100]}"

    status: str = "EXACT" if eval_result.exact_match else (
        "ANCESTOR" if eval_result.ancestor_match else (
            "OVER_DEEP" if eval_result.over_deep else "MISS"
        )
    )
    if error:
        status = "ERROR"
    fmt_tag: str = eval_result.format_compliance
    logger.info("  -> 评分: %s | 格式: %s", status, fmt_tag)

    return eval_result


def generate_improvement_suggestions(summary: EvalSummary) -> list[str]:
    """根据失败分析生成改进建议 TOP 3。"""
    suggestions: list[str] = []

    # 按失败原因排序
    sorted_reasons: list[tuple[str, int]] = summary.fail_reasons.most_common()

    reason: str
    count: int
    for reason, count in sorted_reasons:
        if reason == FAIL_FORMAT:
            suggestions.append(
                f"格式合规: {count} 个样本输出格式不规范。"
                "建议在 system.md 中加强格式约束的 few-shot 示例，"
                "或在末尾追加 reminder。"
            )
        elif reason == FAIL_SHALLOW:
            suggestions.append(
                f"定位深度不足: {count} 个样本停得太浅。"
                "建议在 system.md 示例中增加从浅层继续深入的 case，"
                "让模型对明确关键词有更强的向下探索倾向。"
            )
        elif reason == FAIL_WRONG_BRANCH:
            suggestions.append(
                f"分支错误: {count} 个样本走错了分支。"
                "建议检查各节点的 keywords 是否有歧义或重叠，"
                "增加区分性关键词。"
            )
        elif reason == FAIL_NO_STATE_USE:
            suggestions.append(
                f"状态简报被忽略: {count} 个样本没有利用状态简报信息。"
                "建议在 system.md 中强化 '已完成节点不要再定位' 的规则，"
                "增加带状态简报的示例。"
            )
        elif reason == FAIL_OVER_DEEP:
            suggestions.append(
                f"过度下钻: {count} 个样本钻得太深。"
                "建议加强 '不确定就停住' 的规则，"
                "在关键分叉点增加 '需要额外信号才继续' 的约束。"
            )
        elif reason == FAIL_OTHER:
            suggestions.append(
                f"其他失败: {count} 个样本未归入具体类别。"
                "建议逐条分析 raw_output 确定根因。"
            )

    return suggestions[:3]


async def run_evaluation() -> None:
    """运行完整评估流程。"""
    # 1. 加载数据集
    logger.info("加载数据集: %s", _DATASET_PATH)
    samples: list[EvalSample] = load_dataset(_DATASET_PATH)
    logger.info("数据集样本数: %d", len(samples))

    # 2. 加载业务地图
    logger.info("加载业务地图: %s", _BUSINESS_MAP_DIR)
    service: BusinessMapService = BusinessMapService()
    service.load(_BUSINESS_MAP_DIR)
    logger.info("业务地图加载完成")

    # 3. 加载 system prompt
    system_prompt_text: str = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    logger.info("系统提示词长度: %d 字符", len(system_prompt_text))

    # 4. 创建工具
    tools: list[Any] = create_tool_functions(service)

    # 5. 创建模型
    logger.info("创建 LLM 模型...")
    model: Model = create_model()
    logger.info("模型创建完成")

    # 6. 创建 Agent
    agent: Agent[None, str] = Agent(
        model=model,
        system_prompt=system_prompt_text,
        tools=tools,
        retries=1,
    )
    logger.info("Agent 创建完成")

    # 7. 运行评估
    results: list[EvalResult] = []
    summary: EvalSummary = EvalSummary()
    start_time: float = time.time()

    i: int
    sample: EvalSample
    for i, sample in enumerate(samples, 1):
        eval_result: EvalResult = await run_single(agent, sample, i, len(samples))
        results.append(eval_result)

        # 更新汇总
        summary.total += 1
        if eval_result.exact_match:
            summary.exact_match_count += 1
        if eval_result.ancestor_match:
            summary.ancestor_match_count += 1
        if eval_result.over_deep:
            summary.over_deep_count += 1
        if eval_result.error:
            summary.error_count += 1

        # 格式统计
        if eval_result.format_compliance == FORMAT_STRICT:
            summary.format_strict_count += 1
        elif eval_result.format_compliance == FORMAT_RECOVERED:
            summary.format_recovered_count += 1
        else:
            summary.format_invalid_count += 1

        # 按类别统计
        cat: str = sample.category
        if cat not in summary.category_stats:
            summary.category_stats[cat] = CategoryStats()
        stats: CategoryStats = summary.category_stats[cat]
        stats.total += 1
        if eval_result.exact_match:
            stats.exact += 1
        if eval_result.ancestor_match:
            stats.ancestor += 1
        if eval_result.over_deep:
            stats.over_deep += 1
        if eval_result.error:
            stats.error += 1

        # 失败原因统计
        if eval_result.fail_reason:
            summary.fail_reasons[eval_result.fail_reason] += 1
            summary.failures.append(eval_result)

        # 超时检查（15 分钟）
        elapsed: float = time.time() - start_time
        if elapsed > 900:
            logger.warning("已运行 %.0f 秒，超过 15 分钟限制，截断评估", elapsed)
            break

    elapsed_total: float = time.time() - start_time

    # 8. 保存结果
    logger.info("保存结果到: %s", _RESULTS_PATH)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        r: EvalResult
        for r in results:
            record: dict[str, Any] = {
                "id": r.id,
                "category": r.category,
                "subcategory": r.subcategory,
                "user_message": r.user_message,
                "expected_ids": r.expected_ids,
                "actual_ids": r.actual_ids,
                "raw_output": r.raw_output.strip(),
                "exact_match": r.exact_match,
                "ancestor_match": r.ancestor_match,
                "over_deep": r.over_deep,
                "format_compliance": r.format_compliance,
                "fail_reason": r.fail_reason,
                "fail_detail": r.fail_detail,
                "error": r.error,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 9. 打印汇总报告
    print("\n" + "=" * 70)
    print("=== 用户视角评估结果 ===")
    print("=" * 70)
    print(f"数据集样本数:     {len(samples)}")
    print(f"实际评估样本数:   {summary.total}")
    print(f"总耗时:           {elapsed_total:.1f} 秒")
    print(f"平均每样本耗时:   {elapsed_total / max(summary.total, 1):.1f} 秒")
    print()

    # 核心指标
    exact_rate: float = summary.exact_match_count / max(summary.total, 1) * 100
    acceptable_count: int = summary.exact_match_count + summary.ancestor_match_count
    acceptable_rate: float = acceptable_count / max(summary.total, 1) * 100
    over_deep_rate: float = summary.over_deep_count / max(summary.total, 1) * 100
    strict_format_rate: float = summary.format_strict_count / max(summary.total, 1) * 100

    print("总体指标:")
    print(f"  精确匹配率:       {exact_rate:.1f}% ({summary.exact_match_count}/{summary.total})")
    print(f"  总可接受率:       {acceptable_rate:.1f}% ({acceptable_count}/{summary.total})")
    print(f"  过度下钻率:       {over_deep_rate:.1f}% ({summary.over_deep_count}/{summary.total})")
    print(f"  严格格式合规率:   {strict_format_rate:.1f}% ({summary.format_strict_count}/{summary.total})")
    print(f"  格式可恢复:       {summary.format_recovered_count}/{summary.total}")
    print(f"  格式不可用:       {summary.format_invalid_count}/{summary.total}")
    print(f"  错误数:           {summary.error_count}/{summary.total}")
    print()

    # 按类别
    print("按类别:")
    cat_name: str
    cat_stats: CategoryStats
    for cat_name in sorted(summary.category_stats.keys()):
        cat_stats = summary.category_stats[cat_name]
        cat_accept: int = cat_stats.exact + cat_stats.ancestor
        print(
            f"  {cat_name:25s}: "
            f"{cat_stats.exact}/{cat_stats.total} exact, "
            f"{cat_accept}/{cat_stats.total} acceptable"
            f"{', OVER_DEEP=' + str(cat_stats.over_deep) if cat_stats.over_deep else ''}"
            f"{', ERROR=' + str(cat_stats.error) if cat_stats.error else ''}"
        )
    print()

    # 失败分析
    if summary.fail_reasons:
        total_fails: int = sum(summary.fail_reasons.values())
        print("失败分析:")
        reason_name: str
        reason_count: int
        for reason_name, reason_count in summary.fail_reasons.most_common():
            pct: float = reason_count / max(total_fails, 1) * 100
            print(f"  {reason_name:15s}: {reason_count} 个 (占 MISS 的 {pct:.0f}%)")
        print()

    # 代表性失败案例
    if summary.failures:
        print("代表性失败案例:")
        shown: int = 0
        f_case: EvalResult
        for f_case in summary.failures[:10]:
            print(f"  [{f_case.id}] {f_case.category} / {f_case.subcategory}")
            print(f"    用户消息: {f_case.user_message[:60]}")
            print(f"    期望: {f_case.expected_ids}")
            print(f"    实际: {f_case.actual_ids}")
            print(f"    原因: {f_case.fail_reason} - {f_case.fail_detail[:80]}")
            if f_case.raw_output:
                print(f"    原始输出: {f_case.raw_output.strip()[:80]}")
            print()
            shown += 1
        if len(summary.failures) > 10:
            print(f"  ... 还有 {len(summary.failures) - 10} 个失败案例")
        print()

    # 改进建议
    suggestions: list[str] = generate_improvement_suggestions(summary)
    if suggestions:
        print("改进建议 TOP 3:")
        idx: int
        suggestion: str
        for idx, suggestion in enumerate(suggestions, 1):
            print(f"  {idx}. {suggestion}")
        print()

    # 注意事项
    print("--- 注意事项 ---")
    print("- recent_history 在当前实现中为空，代词类后续回合行为未评估")
    print("- 本评估每条样本独立运行，不模拟多轮对话场景")
    print("- 状态简报以文本方式注入，非真实的 state_tree 对象")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_evaluation())

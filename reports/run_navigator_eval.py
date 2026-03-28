"""Navigator 导航定位器真实模型评估脚本。

加载标注数据集，使用真实 LLM 运行 BusinessMapAgent 导航定位，
将结果与预期对比评分，输出评估报告。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
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
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "mainagent" / "business-map"
_SYSTEM_PROMPT_PATH: Path = (
    _PROJECT_ROOT / "subagents" / "business_map_agent" / "prompts" / "templates" / "system.md"
)
_DATASET_PATH: Path = _PROJECT_ROOT / "reports" / "navigator-eval-dataset.jsonl"
_RESULTS_PATH: Path = _PROJECT_ROOT / "reports" / "navigator-eval-results.jsonl"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
logger: logging.Logger = logging.getLogger("navigator_eval")
logger.setLevel(logging.INFO)


# ── 数据模型 ──


@dataclass
class EvalSample:
    """评估数据集的一条样本。"""

    id: str
    category: str
    user_message: str
    state_briefing: str
    expected_ids: list[str]
    acceptable_ancestors: list[str]
    unacceptable_over_deep: list[str]
    rationale: str


@dataclass
class EvalResult:
    """一条样本的评估结果。"""

    id: str
    category: str
    user_message: str
    expected_ids: list[str]
    actual_ids: list[str]
    raw_output: str
    exact_match: bool
    ancestor_match: bool
    over_deep: bool
    multi_path_precision: float
    multi_path_recall: float
    error: str = ""


@dataclass
class EvalSummary:
    """评估汇总指标。"""

    total: int = 0
    exact_match_count: int = 0
    ancestor_match_count: int = 0
    over_deep_count: int = 0
    error_count: int = 0
    multi_path_precision_sum: float = 0.0
    multi_path_recall_sum: float = 0.0
    multi_path_count: int = 0
    category_stats: dict[str, dict[str, int]] = field(default_factory=dict)


# ── 业务地图工具函数（不依赖 AgentDeps，直接绑定 service） ──


def create_tool_functions(service: BusinessMapService) -> list[Any]:
    """创建纯函数版工具（pydantic_ai.Agent 原生格式，不需要 RunContext）。"""

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


# ── 输出解析 ──


def parse_node_ids(raw_output: str) -> list[str]:
    """从模型原始输出中解析节点 ID 列表。

    处理多种输出格式：
    - 纯 ID：project_saving
    - 逗号分隔：confirm_saving, search
    - JSON 混合：{"node_id":"root"}\nproject_saving
    - 多行混合输出
    """
    import re

    # 业务地图中所有有效的节点 ID
    valid_node_ids: set[str] = {
        "root", "project_saving", "confirm_project", "direct_expression",
        "fuzzy_intent", "symptom_based", "confirm_requirements", "confirm_saving",
        "coupon_path", "bidding_path", "merchant_search", "search", "compare",
        "confirm", "booking", "build_plan", "execute",
    }

    cleaned: str = raw_output.strip()

    # 去掉 markdown code block
    if cleaned.startswith("```"):
        lines: list[str] = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    # 策略1：尝试从输出的最后一行提取（模型通常最后输出答案）
    output_lines: list[str] = [
        line.strip() for line in cleaned.split("\n") if line.strip()
    ]

    # 策略2：提取所有出现的有效 node_id（使用 word boundary）
    all_found_ids: list[str] = []
    node_id: str
    for node_id in valid_node_ids:
        # 用 word boundary 匹配，避免 "confirm" 误匹配 "confirm_project" 的一部分
        pattern: str = r'\b' + re.escape(node_id) + r'\b'
        if re.search(pattern, cleaned):
            all_found_ids.append(node_id)

    # 策略3：如果最后一行是纯 ID 格式（逗号分隔的 node_id），优先使用
    if output_lines:
        last_line: str = output_lines[-1]
        # 去掉可能的括号和 JSON 标记
        if not last_line.startswith("{") and not last_line.startswith("["):
            last_line_ids: list[str] = []
            candidate: str
            for candidate in re.split(r'[,\s]+', last_line):
                candidate = candidate.strip()
                if candidate in valid_node_ids:
                    last_line_ids.append(candidate)
            if last_line_ids:
                return last_line_ids

    # 策略4：去除中间的工具调用 JSON 块，只看非 JSON 行中出现的 ID
    non_json_ids: list[str] = []
    line: str
    for line in output_lines:
        stripped: str = line.strip()
        # 跳过 JSON 行
        if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("}") or stripped.startswith("]"):
            continue
        # 跳过明显的解释性文字（含中文标点或长于50字符）
        if len(stripped) > 50 and any(c in stripped for c in "。，？！（）"):
            continue
        for nid in valid_node_ids:
            pattern_str: str = r'\b' + re.escape(nid) + r'\b'
            if re.search(pattern_str, stripped):
                if nid not in non_json_ids:
                    non_json_ids.append(nid)

    if non_json_ids:
        return non_json_ids

    # 策略5：fallback 到所有找到的 ID，但过滤祖先/后代关系——只保留最深的
    if all_found_ids:
        # 过滤：如果 A 是 B 的祖先，只保留 B
        filtered: list[str] = []
        fid: str
        for fid in all_found_ids:
            # 检查是否有其他找到的 ID 是这个 ID 的后代
            is_ancestor_of_another: bool = any(
                fid in ANCESTOR_MAP.get(other_id, [])
                for other_id in all_found_ids
                if other_id != fid
            )
            if not is_ancestor_of_another:
                filtered.append(fid)

        # 如果过滤后得到了 root 的所有直接子节点（3个），这通常表示
        # 模型只是回显了 get_business_children("root") 的返回值，
        # 不应视为有效定位结果
        root_children: set[str] = {"project_saving", "merchant_search", "booking"}
        if root_children.issubset(set(filtered)):
            # 模型没有真正定位，返回空
            return []

        return filtered if filtered else all_found_ids

    return []


# ── 评分逻辑 ──


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


def score_sample(sample: EvalSample, actual_ids: list[str]) -> EvalResult:
    """对单条样本评分。"""
    expected_set: set[str] = set(sample.expected_ids)
    actual_set: set[str] = set(actual_ids)

    # exact_match: 完全一致（顺序无关）
    exact_match: bool = expected_set == actual_set

    # ancestor_match: 所有 actual_id 都是 expected_id 的有效祖先
    ancestor_match: bool = False
    if not exact_match and actual_ids:
        acceptable_set: set[str] = set(sample.acceptable_ancestors) | expected_set
        ancestor_match = all(aid in acceptable_set for aid in actual_ids)

    # over_deep: actual 中包含不可接受的过深节点
    over_deep: bool = bool(
        actual_set & set(sample.unacceptable_over_deep)
    )

    # multi_path precision/recall
    multi_path_precision: float = 0.0
    multi_path_recall: float = 0.0
    if len(sample.expected_ids) > 1 or len(actual_ids) > 1:
        if actual_ids:
            # precision: actual 中有多少是 expected 或可接受祖先
            acceptable_full: set[str] = expected_set | set(sample.acceptable_ancestors)
            correct_in_actual: int = sum(
                1 for aid in actual_ids if aid in acceptable_full
            )
            multi_path_precision = correct_in_actual / len(actual_ids)
        if sample.expected_ids:
            # recall: expected 中有多少出现在 actual
            found: int = sum(
                1 for eid in sample.expected_ids if eid in actual_set
            )
            multi_path_recall = found / len(sample.expected_ids)
    else:
        # 单路径：如果匹配就是 1.0
        if exact_match or ancestor_match:
            multi_path_precision = 1.0
            multi_path_recall = 1.0

    return EvalResult(
        id=sample.id,
        category=sample.category,
        user_message=sample.user_message,
        expected_ids=sample.expected_ids,
        actual_ids=actual_ids,
        raw_output="",  # 填充在调用处
        exact_match=exact_match,
        ancestor_match=ancestor_match,
        over_deep=over_deep,
        multi_path_precision=multi_path_precision,
        multi_path_recall=multi_path_recall,
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
    logger.info("[%d/%d] %s | 用户消息: %s", index, total, sample.id, sample.user_message[:50])

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

    eval_result: EvalResult = score_sample(sample, actual_ids)
    eval_result.raw_output = raw_output
    eval_result.error = error

    status: str = "EXACT" if eval_result.exact_match else (
        "ANCESTOR" if eval_result.ancestor_match else (
            "OVER_DEEP" if eval_result.over_deep else "MISS"
        )
    )
    if error:
        status = "ERROR"
    logger.info("  -> 评分: %s", status)

    return eval_result


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

        # 多路径统计
        if len(sample.expected_ids) > 1:
            summary.multi_path_count += 1
            summary.multi_path_precision_sum += eval_result.multi_path_precision
            summary.multi_path_recall_sum += eval_result.multi_path_recall

        # 分类统计
        cat: str = sample.category
        if cat not in summary.category_stats:
            summary.category_stats[cat] = {
                "total": 0,
                "exact": 0,
                "ancestor": 0,
                "over_deep": 0,
                "error": 0,
            }
        summary.category_stats[cat]["total"] += 1
        if eval_result.exact_match:
            summary.category_stats[cat]["exact"] += 1
        if eval_result.ancestor_match:
            summary.category_stats[cat]["ancestor"] += 1
        if eval_result.over_deep:
            summary.category_stats[cat]["over_deep"] += 1
        if eval_result.error:
            summary.category_stats[cat]["error"] += 1

        # 超时检查
        elapsed: float = time.time() - start_time
        if elapsed > 600:  # 10 分钟
            logger.warning("已运行 %.0f 秒，超过 10 分钟限制，截断评估", elapsed)
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
                "user_message": r.user_message,
                "expected_ids": r.expected_ids,
                "actual_ids": r.actual_ids,
                "raw_output": r.raw_output.strip(),
                "exact_match": r.exact_match,
                "ancestor_match": r.ancestor_match,
                "over_deep": r.over_deep,
                "multi_path_precision": r.multi_path_precision,
                "multi_path_recall": r.multi_path_recall,
                "error": r.error,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 9. 打印汇总报告
    print("\n" + "=" * 70)
    print("Navigator 导航定位器评估报告")
    print("=" * 70)
    print(f"数据集样本数:     {len(samples)}")
    print(f"实际评估样本数:   {summary.total}")
    print(f"总耗时:           {elapsed_total:.1f} 秒")
    print(f"平均每样本耗时:   {elapsed_total / max(summary.total, 1):.1f} 秒")
    print()

    # 核心指标
    exact_rate: float = summary.exact_match_count / max(summary.total, 1) * 100
    ancestor_rate: float = summary.ancestor_match_count / max(summary.total, 1) * 100
    acceptable_rate: float = (summary.exact_match_count + summary.ancestor_match_count) / max(summary.total, 1) * 100
    over_deep_rate: float = summary.over_deep_count / max(summary.total, 1) * 100
    error_rate: float = summary.error_count / max(summary.total, 1) * 100

    print("--- 核心指标 ---")
    print(f"精确匹配率 (exact_match):          {exact_rate:.1f}% ({summary.exact_match_count}/{summary.total})")
    print(f"祖先可接受匹配率 (ancestor_match):  {ancestor_rate:.1f}% ({summary.ancestor_match_count}/{summary.total})")
    print(f"总可接受率 (exact + ancestor):      {acceptable_rate:.1f}% ({summary.exact_match_count + summary.ancestor_match_count}/{summary.total})")
    print(f"过深错误率 (over_deep):             {over_deep_rate:.1f}% ({summary.over_deep_count}/{summary.total})")
    print(f"错误率 (error):                     {error_rate:.1f}% ({summary.error_count}/{summary.total})")

    # 多路径指标
    if summary.multi_path_count > 0:
        avg_precision: float = summary.multi_path_precision_sum / summary.multi_path_count
        avg_recall: float = summary.multi_path_recall_sum / summary.multi_path_count
        print()
        print("--- 多路径指标 ---")
        print(f"多路径样本数:    {summary.multi_path_count}")
        print(f"平均 precision:  {avg_precision:.3f}")
        print(f"平均 recall:     {avg_recall:.3f}")

    # 分类细分
    print()
    print("--- 分类细分 ---")
    cat_name: str
    stats: dict[str, int]
    for cat_name, stats in sorted(summary.category_stats.items()):
        cat_total: int = stats["total"]
        cat_exact: int = stats["exact"]
        cat_ancestor: int = stats["ancestor"]
        cat_over_deep: int = stats["over_deep"]
        cat_error: int = stats["error"]
        cat_accept: int = cat_exact + cat_ancestor
        print(
            f"  {cat_name:20s}: "
            f"total={cat_total:2d}  "
            f"exact={cat_exact:2d} ({cat_exact / max(cat_total, 1) * 100:5.1f}%)  "
            f"accept={cat_accept:2d} ({cat_accept / max(cat_total, 1) * 100:5.1f}%)  "
            f"over_deep={cat_over_deep:2d}  "
            f"error={cat_error:2d}"
        )

    # 失败案例分析
    failures: list[EvalResult] = [
        r for r in results
        if not r.exact_match and not r.ancestor_match
    ]
    if failures:
        print()
        print("--- 代表性失败案例 ---")
        shown: int = 0
        f_case: EvalResult
        for f_case in failures[:10]:
            print(f"  [{f_case.id}] {f_case.category}")
            print(f"    用户消息: {f_case.user_message[:60]}")
            print(f"    期望: {f_case.expected_ids}")
            print(f"    实际: {f_case.actual_ids}")
            if f_case.over_deep:
                print(f"    !!! 过深错误")
            if f_case.error:
                print(f"    错误: {f_case.error[:100]}")
            print()
            shown += 1
        if len(failures) > 10:
            print(f"  ... 还有 {len(failures) - 10} 个失败案例")

    # history-dependent 声明
    print()
    print("--- 注意事项 ---")
    print("- recent_history 在当前实现中为空，代词类后续回合行为未评估")
    print("  例如：'那个'、'就它了'、'上面那家' 等依赖对话上下文的指代")
    print("- 本评估每条样本独立运行，不模拟多轮对话场景")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_evaluation())

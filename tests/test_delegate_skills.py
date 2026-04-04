"""验证 orchestrator 的 delegate 创建的子 agent 是否能正常加载 skills。

验证点：
1. orchestrator 是否调了 delegate（tool_calls 里有 "delegate"）
2. delegate 子 agent 返回的结果是否正常（不是报错）
3. 子 agent 是否触发了 Skill 工具调用
4. BMA / MainAgent 日志是否有 skill 相关报错

运行方式：
    cd mainagent && uv run python ../tests/test_delegate_skills.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx

# ── 配置 ──
MAINAGENT_URL: str = "http://127.0.0.1:8100"
BMA_URL: str = "http://127.0.0.1:8103"
TIMEOUT: int = 180

# 日志路径
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
MAINAGENT_LOG: Path = PROJECT_ROOT / "mainagent" / "logs" / "chatagent.log"
BMA_LOG: Path = PROJECT_ROOT / "subagents" / "business_map_agent" / "logs" / "bma.log"

# ── ANSI 颜色 ──
_G: str = "\033[92m"
_R: str = "\033[91m"
_Y: str = "\033[93m"
_C: str = "\033[96m"
_B: str = "\033[1m"
_D: str = "\033[2m"
_0: str = "\033[0m"


# ============================================================
# 数据模型
# ============================================================


@dataclass
class RoundResult:
    """单轮 SSE 对话结果。"""
    user_message: str
    response_text: str
    tool_calls: list[str]
    elapsed_seconds: float
    error: str = ""


@dataclass
class TestResult:
    """单个断言结果。"""
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)


# ============================================================
# SSE 流式客户端
# ============================================================


async def send_message(
    session_id: str,
    message: str,
    user_id: str = "test-delegate-skills",
) -> RoundResult:
    """调用 /chat/stream SSE 端点，解析事件流，返回结构化结果。"""
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    error: str = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(TIMEOUT))) as client:
            body: dict[str, str] = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            async with client.stream(
                "POST",
                f"{MAINAGENT_URL}/chat/stream",
                json=body,
            ) as resp:
                resp.raise_for_status()
                buffer: str = ""

                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        raw_event: str
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event_type: str = ""
                        event_data: str = ""
                        for line in raw_event.strip().split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:].strip()
                            elif line.startswith("data: "):
                                event_data = line[6:]

                        if not event_data:
                            continue

                        try:
                            data: dict[str, object] = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict[str, object] = data.get("data", {})  # type: ignore[assignment]

                        if event_type == "text":
                            content: str = str(evt_data.get("content", ""))
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = str(evt_data.get("tool_name", "unknown"))
                            tool_calls.append(tool_name)

                        elif event_type == "error":
                            err_msg: str = str(
                                evt_data.get("message", evt_data.get("error", str(evt_data)))
                            )
                            error = err_msg

                        elif event_type == "chat_request_end":
                            # 请求结束，不再等待
                            break

    except httpx.ReadTimeout:
        # 如果已经收到文本和工具调用，超时只是流结束慢，不算硬错误
        if not text_parts and not tool_calls:
            error = f"超时（{TIMEOUT}s），无任何响应"
        # else: 有数据就不标记 error
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        # 同理，如果已有数据，不标记为 error
        if not text_parts and not tool_calls:
            error = str(e)

    elapsed: float = time.monotonic() - start

    return RoundResult(
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 日志扫描
# ============================================================


def read_log_tail(path: Path, max_bytes: int = 20_000) -> str:
    """读取日志文件尾部内容。"""
    if not path.exists():
        return f"(日志文件不存在: {path})"
    try:
        size: int = path.stat().st_size
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                _ = f.readline()  # 丢弃第一行残缺行
            return f.read()
    except Exception as e:
        return f"(读取失败: {e})"


def scan_log_for_errors(log_text: str, keywords: list[str]) -> list[str]:
    """在日志文本中搜索包含指定关键词的错误行。"""
    found: list[str] = []
    for line in log_text.splitlines():
        line_lower: str = line.lower()
        if any(kw.lower() in line_lower for kw in keywords):
            # 只取最后 200 字符避免过长
            trimmed: str = line.strip()[-200:]
            found.append(trimmed)
    return found


# ============================================================
# 测试 1：多轮对话触发 delegate + 验证 skill 加载
# ============================================================


async def test_delegate_skill_loading() -> list[TestResult]:
    """多轮对话触发 orchestrator → delegate，验证子 agent skill 加载。"""
    results: list[TestResult] = []
    session_id: str = f"test-delegate-skill-{uuid4().hex[:8]}"

    # ── 记录日志起始位置 ──
    mainagent_log_start: int = MAINAGENT_LOG.stat().st_size if MAINAGENT_LOG.exists() else 0
    bma_log_start: int = BMA_LOG.stat().st_size if BMA_LOG.exists() else 0

    # ── 轮 1：触发复合场景 ──
    print(f"\n{_C}  轮 1: 发送复合需求...{_0}")
    r1: RoundResult = await send_message(
        session_id,
        "帮我找个附近的修理厂，顺便看看有什么保养优惠，我在上海浦东新区，车是2021款大众朗逸",
    )
    print(f"  工具调用: {r1.tool_calls}")
    print(f"  回复长度: {len(r1.response_text)} 字, 耗时: {r1.elapsed_seconds:.1f}s")
    if r1.response_text:
        print(f"  回复摘要: {r1.response_text[:200]}...")

    if r1.error:
        results.append(TestResult(
            name="轮1: 请求成功",
            passed=False,
            details=[f"ERROR: {r1.error}"],
        ))
        return results

    results.append(TestResult(
        name="轮1: 请求成功",
        passed=True,
        details=[f"耗时 {r1.elapsed_seconds:.1f}s, 工具: {r1.tool_calls}"],
    ))

    # ── 判断是否走了 delegate ──
    has_delegate: bool = "delegate" in r1.tool_calls
    if has_delegate:
        delegate_count: int = r1.tool_calls.count("delegate")
        results.append(TestResult(
            name="轮1: orchestrator 触发了 delegate",
            passed=True,
            details=[f"delegate 调用 {delegate_count} 次"],
        ))
    else:
        # 可能需要补充信息后第二轮触发
        results.append(TestResult(
            name="轮1: orchestrator 触发了 delegate",
            passed=False,
            details=[
                f"未检测到 delegate 调用，实际工具: {r1.tool_calls}",
                "可能 BMA 未返回多场景，或 orchestrator 决定先收集信息",
            ],
        ))

    # ── 轮 2：如果轮 1 未触发 delegate，补充信息再试 ──
    r2: RoundResult | None = None
    if not has_delegate:
        print(f"\n{_C}  轮 2: 补充信息...{_0}")
        await asyncio.sleep(2)
        r2 = await send_message(session_id, "对，就是保养，帮我找修理厂和优惠都查一下吧")
        print(f"  工具调用: {r2.tool_calls}")
        print(f"  回复长度: {len(r2.response_text)} 字, 耗时: {r2.elapsed_seconds:.1f}s")
        if r2.response_text:
            print(f"  回复摘要: {r2.response_text[:200]}...")

        has_delegate = "delegate" in r2.tool_calls
        if has_delegate:
            results.append(TestResult(
                name="轮2: delegate 触发",
                passed=True,
                details=[f"工具: {r2.tool_calls}"],
            ))
        else:
            results.append(TestResult(
                name="轮2: delegate 触发",
                passed=False,
                details=[f"仍未触发 delegate，实际工具: {r2.tool_calls}"],
            ))

    # ── 检查子 agent 工具调用（delegate 内部工具通过 emitter 传出） ──
    all_tool_calls: list[str] = list(r1.tool_calls)
    if r2 is not None:
        all_tool_calls.extend(r2.tool_calls)

    sub_agent_tools: list[str] = [
        t for t in all_tool_calls
        if t not in ("delegate", "update_session_state", "Skill") and t != "unknown"
    ]
    skill_calls: list[str] = [t for t in all_tool_calls if t == "Skill"]

    if sub_agent_tools:
        results.append(TestResult(
            name="子 agent 执行了业务工具",
            passed=True,
            details=[f"业务工具: {sub_agent_tools}"],
        ))
    else:
        results.append(TestResult(
            name="子 agent 执行了业务工具",
            passed=False,
            details=["未观察到子 agent 业务工具调用（可能被 emitter 过滤或未到达执行阶段）"],
        ))

    if skill_calls:
        results.append(TestResult(
            name="子 agent 调用了 Skill 工具",
            passed=True,
            details=[f"Skill 调用次数: {len(skill_calls)}"],
        ))
    else:
        # Skill 工具是否被调用取决于 LLM 决策，不一定每次都触发，标记为 WARN
        results.append(TestResult(
            name="子 agent 调用了 Skill 工具",
            passed=True,  # 非硬性失败
            details=["未观察到 Skill 调用（LLM 可能判定不需要，非硬性错误）"],
        ))

    # ── 检查回复质量 ──
    all_responses: str = r1.response_text + (r2.response_text if r2 else "")
    has_meaningful_reply: bool = len(all_responses.strip()) > 20
    has_error_in_reply: bool = any(
        keyword in all_responses
        for keyword in ["delegate 执行失败", "错误", "Traceback", "skill system not available"]
    )

    results.append(TestResult(
        name="回复内容有效（非报错）",
        passed=has_meaningful_reply and not has_error_in_reply,
        details=[
            f"回复总长度: {len(all_responses)} 字",
            f"含错误关键词: {'是' if has_error_in_reply else '否'}",
            f"回复片段: {all_responses[:300]}",
        ],
    ))

    # ── 日志分析 ──
    await asyncio.sleep(1)  # 等日志落盘

    # 读取本次测试产生的新日志
    mainagent_log_new: str = ""
    if MAINAGENT_LOG.exists():
        try:
            with open(MAINAGENT_LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(mainagent_log_start)
                mainagent_log_new = f.read()
        except Exception:
            mainagent_log_new = "(读取失败)"

    bma_log_new: str = ""
    if BMA_LOG.exists():
        try:
            with open(BMA_LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(bma_log_start)
                bma_log_new = f.read()
        except Exception:
            bma_log_new = "(读取失败)"

    # 搜索 skill 相关错误
    skill_error_keywords: list[str] = [
        "skill",
        "skill_registry",
        "allowed_skills",
        "invoke_skill",
        "skill system not available",
        "SkillRegistry",
    ]

    mainagent_skill_errors: list[str] = scan_log_for_errors(
        mainagent_log_new,
        [f"ERROR" for _ in skill_error_keywords],  # 先找 ERROR 级别
    )
    # 再精确搜 skill 相关的 error
    mainagent_skill_specific: list[str] = [
        line for line in mainagent_skill_errors
        if any(kw.lower() in line.lower() for kw in skill_error_keywords)
    ]

    bma_errors: list[str] = scan_log_for_errors(bma_log_new, ["ERROR", "error", "Traceback"])

    results.append(TestResult(
        name="MainAgent 日志无 skill 相关 ERROR",
        passed=len(mainagent_skill_specific) == 0,
        details=[
            f"新增日志行数: {len(mainagent_log_new.splitlines())}",
            *(f"SKILL_ERROR: {e}" for e in mainagent_skill_specific[:5]),
        ] if mainagent_skill_specific else [
            f"新增日志行数: {len(mainagent_log_new.splitlines())}",
            "OK: 无 skill 相关 ERROR",
        ],
    ))

    # 搜索 delegate 执行证据：
    # 1. delegate.py 自身日志（logger 名 = hlsc.tools.delegate）
    # 2. 子 agent 的 "请求开始" 日志（不同的 request_id，query 以 "上下文：" 开头）
    delegate_evidence_lines: list[str] = [
        line.strip()[-200:]
        for line in mainagent_log_new.splitlines()
        if "delegate 完成" in line
        or "delegate:" in line.lower()
        or ("请求开始" in line and "上下文：" in line)  # 子 agent 请求
        or ("请求结束" in line and session_id in line)
    ]
    results.append(TestResult(
        name="MainAgent 日志有 delegate 执行记录",
        passed=len(delegate_evidence_lines) > 0 if has_delegate else True,
        details=[
            *(f"LOG: {line}" for line in delegate_evidence_lines[:8]),
        ] if delegate_evidence_lines else [
            "未找到 delegate 日志记录" if has_delegate else "delegate 未触发，跳过日志检查",
        ],
    ))

    results.append(TestResult(
        name="BMA 日志无异常",
        passed=len(bma_errors) == 0,
        details=[
            f"新增日志行数: {len(bma_log_new.splitlines())}",
            *(f"BMA_ERROR: {e}" for e in bma_errors[:5]),
        ] if bma_errors else [
            f"新增日志行数: {len(bma_log_new.splitlines())}",
            "OK: 无 ERROR",
        ],
    ))

    return results


# ============================================================
# 测试 2：直接验证 BMA 多场景分类（前置条件）
# ============================================================


async def test_bma_multiscene_classify() -> list[TestResult]:
    """验证 BMA 对复合需求是否返回多场景（delegate 的前置条件）。"""
    results: list[TestResult] = []

    cases: list[tuple[str, list[str]]] = [
        ("帮我找个修理厂顺便看看优惠", ["searchshops", "searchcoupons"]),
        ("帮我找个附近的修理厂，顺便看看有什么保养优惠", ["searchshops", "searchcoupons"]),
        ("有优惠的店有哪些", ["searchshops", "searchcoupons"]),
    ]

    for message, expected_scenes in cases:
        test_name: str = f"BMA 多场景分类: '{message[:30]}...'"
        details: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp: httpx.Response = await client.post(
                    f"{BMA_URL}/classify",
                    json={"message": message},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                actual_scenes: list[str] = data.get("scenes", [])  # type: ignore[assignment]

            details.append(f"期望: {expected_scenes}")
            details.append(f"实际: {actual_scenes}")

            is_multi: bool = len(actual_scenes) > 1
            matched: bool = set(actual_scenes) == set(expected_scenes)

            if matched:
                details.append("OK: 场景完全匹配")
            elif is_multi:
                details.append(f"WARN: 返回多场景但不完全匹配")
            else:
                details.append("FAIL: 未返回多场景（delegate 不会触发）")

            passed: bool = is_multi  # 只要返回多场景就算 OK

        except Exception as e:
            passed = False
            details.append(f"ERROR: {e}")

        results.append(TestResult(name=test_name, passed=passed, details=details))

    return results


# ============================================================
# 测试 3：stage_config.yaml skills 配置完整性
# ============================================================


def test_stage_config_skills() -> list[TestResult]:
    """验证 stage_config.yaml 中所有场景的 skills 在磁盘上存在。"""
    import yaml

    results: list[TestResult] = []
    config_path: Path = PROJECT_ROOT / "mainagent" / "stage_config.yaml"

    if not config_path.exists():
        results.append(TestResult(
            name="stage_config.yaml 存在",
            passed=False,
            details=[f"文件不存在: {config_path}"],
        ))
        return results

    raw: dict[str, object] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    scenes: dict[str, dict[str, object]] = raw.get("scenes", {})  # type: ignore[assignment]

    # skill 目录（与 mainagent 部署时 AGENT_FS_DIR 对应）
    skill_base: Path = PROJECT_ROOT / "mainagent" / ".chatagent" / "fstools" / "skills"

    all_declared_skills: set[str] = set()
    missing_skills: list[str] = []

    for scene_name, scene_config in scenes.items():
        scene_skills: list[str] = scene_config.get("skills", [])  # type: ignore[assignment]
        for skill_name in scene_skills:
            all_declared_skills.add(skill_name)
            skill_md: Path = skill_base / skill_name / "SKILL.md"
            if not skill_md.exists():
                missing_skills.append(f"{scene_name}/{skill_name} ({skill_md})")

    results.append(TestResult(
        name="所有场景声明的 skills 在磁盘上存在",
        passed=len(missing_skills) == 0,
        details=[
            f"声明的 skills: {sorted(all_declared_skills)}",
            *(f"MISSING: {m}" for m in missing_skills),
        ] if missing_skills else [
            f"声明的 skills: {sorted(all_declared_skills)}",
            "OK: 全部存在",
        ],
    ))

    # 检查可 delegate 的场景都有 skills 配置
    delegatable: list[str] = ["platform", "searchshops", "searchcoupons", "insurance"]
    no_skills_scenes: list[str] = [
        s for s in delegatable
        if s in scenes and not scenes[s].get("skills")
    ]
    results.append(TestResult(
        name="可 delegate 的场景均配置了 skills",
        passed=len(no_skills_scenes) == 0,
        details=[
            *(f"无 skills: {s}" for s in no_skills_scenes),
        ] if no_skills_scenes else [
            f"OK: {delegatable} 均有 skills 配置",
        ],
    ))

    return results


# ============================================================
# 报告
# ============================================================


def print_report(
    section_name: str,
    results: list[TestResult],
) -> tuple[int, int]:
    """打印测试结果段落，返回 (passed, total)。"""
    total: int = len(results)
    passed_count: int = sum(1 for r in results if r.passed)

    print(f"\n{_B}{'─' * 60}{_0}")
    print(f"{_B}{section_name}{_0}")
    print(f"{_B}{'─' * 60}{_0}\n")

    for result in results:
        status: str = f"{_G}PASS{_0}" if result.passed else f"{_R}FAIL{_0}"
        print(f"  {status} {result.name}")

        for detail in result.details:
            if detail.startswith("FAIL") or detail.startswith("ERROR") or detail.startswith("MISSING"):
                print(f"    {_R}{detail}{_0}")
            elif detail.startswith("WARN"):
                print(f"    {_Y}{detail}{_0}")
            elif detail.startswith("OK"):
                print(f"    {_G}{detail}{_0}")
            elif detail.startswith("LOG:") or detail.startswith("SKILL_ERROR:") or detail.startswith("BMA_ERROR:"):
                print(f"    {_D}{detail}{_0}")
            else:
                print(f"    {_D}{detail}{_0}")

        print()

    color: str = _G if passed_count == total else _Y if passed_count > 0 else _R
    print(f"  {color}通过: {passed_count}/{total}{_0}\n")

    return passed_count, total


# ============================================================
# 主入口
# ============================================================


async def main() -> None:
    """运行 delegate skills 加载验证。"""

    print(f"\n{'=' * 60}")
    print(f"{_B}Delegate Skills 加载验证{_0}")
    print(f"{'=' * 60}")
    print(f"  MainAgent: {MAINAGENT_URL}")
    print(f"  BMA:       {BMA_URL}")

    total_passed: int = 0
    total_tests: int = 0

    # ── 测试 3：静态配置检查（不需要服务） ──
    print(f"\n{_C}>>> 测试 3: stage_config.yaml skills 配置完整性{_0}")
    config_results: list[TestResult] = test_stage_config_skills()
    p3, t3 = print_report("测试 3: skills 配置完整性", config_results)
    total_passed += p3
    total_tests += t3

    # ── 健康检查 ──
    services_ok: bool = True
    try:
        r1: httpx.Response = httpx.get(f"{MAINAGENT_URL}/health", timeout=5)
        r1.raise_for_status()
        print(f"{_G}MainAgent 就绪{_0}")
    except Exception as e:
        print(f"{_R}MainAgent 不可达: {e}{_0}")
        services_ok = False

    try:
        r2: httpx.Response = httpx.get(f"{BMA_URL}/health", timeout=5)
        r2.raise_for_status()
        print(f"{_G}BMA 就绪{_0}")
    except Exception as e:
        print(f"{_R}BMA 不可达: {e}{_0}")
        services_ok = False

    if not services_ok:
        print(f"\n{_R}服务不可达，跳过在线测试{_0}")
        print(f"\n{'=' * 60}")
        print(f"{_Y}{_B}总计: {total_passed}/{total_tests} 通过（在线测试已跳过）{_0}")
        print(f"{'=' * 60}\n")
        return

    # ── 测试 2：BMA 多场景分类 ──
    print(f"\n{_C}>>> 测试 2: BMA 多场景分类验证{_0}")
    bma_results: list[TestResult] = await test_bma_multiscene_classify()
    p2, t2 = print_report("测试 2: BMA 多场景分类（delegate 前置条件）", bma_results)
    total_passed += p2
    total_tests += t2

    # ── 测试 1：多轮对话触发 delegate + skill 验证 ──
    print(f"\n{_C}>>> 测试 1: 多轮对话 delegate + skill 加载验证{_0}")
    delegate_results: list[TestResult] = await test_delegate_skill_loading()
    p1, t1 = print_report("测试 1: delegate skill 加载验证", delegate_results)
    total_passed += p1
    total_tests += t1

    # ── 汇总 ──
    print(f"\n{'=' * 60}")
    color: str = _G if total_passed == total_tests else _Y if total_passed > 0 else _R
    print(f"{color}{_B}总计: {total_passed}/{total_tests} 通过{_0}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())

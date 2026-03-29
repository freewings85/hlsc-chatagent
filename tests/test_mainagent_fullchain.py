"""MainAgent 全链路多轮测试

通过 POST /chat/sync 调用 MainAgent，验证完整链路：
hook → BMA 导航 → 切片组装 → 注入 LLM → LLM 按 checklist 回复。

重点：多轮同 session 对话，验证状态推进和切片切换。

运行方式：
    cd /path/to/project
    mainagent/.venv/bin/python tests/test_mainagent_fullchain.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

MAINAGENT_URL: str = "http://localhost:8100"
# state_tree 存储路径
STATE_TREE_BASE: str = "mainagent/data/inner/test-user/sessions"

# ── ANSI 颜色 ──
_G: str = "\033[92m"   # green
_R: str = "\033[91m"   # red
_Y: str = "\033[93m"   # yellow
_C: str = "\033[96m"   # cyan
_B: str = "\033[1m"    # bold
_D: str = "\033[2m"    # dim
_0: str = "\033[0m"    # reset


async def call_mainagent(
    message: str,
    session_id: str,
) -> dict[str, Any]:
    """调用 MainAgent /chat/sync 端点，返回完整响应。"""
    request_body: dict[str, Any] = {
        "session_id": session_id,
        "message": message,
        "user_id": "test-user",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp: httpx.Response = await client.post(
            f"{MAINAGENT_URL}/chat/sync", json=request_body
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    return data


def read_state_tree(session_id: str) -> str | None:
    """读取 session 的 state_tree.md 文件。"""
    path: Path = Path(STATE_TREE_BASE) / session_id / "state_tree.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


@dataclass
class RoundSpec:
    """单轮对话规格。"""
    message: str
    expect_keywords: list[str]   # 回复中期望命中至少一个
    expect_phase: str             # 期望所处的业务阶段（用于日志标注）


@dataclass
class MultiTurnSequence:
    """多轮对话测试序列。"""
    name: str
    description: str
    rounds: list[RoundSpec]


SEQUENCES: list[MultiTurnSequence] = [
    # ── 序列 A：正常推进流程 ──
    MultiTurnSequence(
        name="序列A-正常推进",
        description="T1项目梳理 → 项目确认 → 省钱方案 → 商户搜索，验证完整推进流程",
        rounds=[
            RoundSpec(
                message="我的车该换机油了",
                expect_keywords=["车型", "车辆", "什么车", "哪款车", "机油", "保养", "项目", "机滤"],
                expect_phase="T1-项目梳理：询问车型/确认项目",
            ),
            RoundSpec(
                message="就做个小保养吧，换机油和机滤",
                expect_keywords=["小保养", "机油", "机滤", "确认", "好的", "明白", "了解", "价格", "费用"],
                expect_phase="T1-项目确认：确认小保养内容",
            ),
            RoundSpec(
                message="有没有优惠活动",
                expect_keywords=["优惠", "省钱", "折扣", "活动", "券", "价格", "方案", "便宜", "划算", "省"],
                expect_phase="T1-省钱方案：展示优惠信息",
            ),
            RoundSpec(
                message="帮我找个店吧",
                expect_keywords=["位置", "地址", "附近", "搜索", "商户", "店", "区域", "哪里", "推荐"],
                expect_phase="T2-商户搜索：搜索/推荐门店",
            ),
        ],
    ),
    # ── 序列 B：中途跳跃 ──
    MultiTurnSequence(
        name="序列B-中途跳跃",
        description="T1保养 → 跳到 T3洗车，验证意图切换",
        rounds=[
            RoundSpec(
                message="我想做个保养",
                expect_keywords=["车型", "车辆", "什么车", "机油", "保养", "项目", "确认"],
                expect_phase="T1-项目梳理：进入保养流程",
            ),
            RoundSpec(
                message="算了不做了，就洗个车吧",
                expect_keywords=["洗车", "预约", "时间", "门店", "什么时候", "哪里", "清洗"],
                expect_phase="T3-洗车：跳转到洗车流程",
            ),
        ],
    ),
]


async def run_all() -> None:
    """执行全部多轮序列测试。"""
    print(f"\n{'='*70}")
    print(f"{_B}{_C}MainAgent 全链路多轮测试 (hook -> BMA -> slice -> LLM){_0}")
    print(f"{'='*70}")
    print(f"目标: {MAINAGENT_URL}\n")

    # 健康检查
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r: httpx.Response = await c.get(f"{MAINAGENT_URL}/.well-known/agent.json")
            r.raise_for_status()
        print(f"{_G}MainAgent 连通{_0}\n")
    except Exception as e:
        print(f"{_R}无法连接 MainAgent: {e}{_0}")
        sys.exit(1)

    total_passed: int = 0
    total_failed: int = 0
    all_results: list[tuple[str, int, str, bool, str]] = []

    for seq in SEQUENCES:
        print(f"\n{_B}{'='*70}{_0}")
        print(f"{_B}{_C}{seq.name}{_0}")
        print(f"  {_D}{seq.description}{_0}")
        print(f"{_B}{'='*70}{_0}\n")

        sid: str = f"test-multi-{uuid4().hex[:8]}"
        print(f"  Session ID: {sid}\n")

        for round_idx, rnd in enumerate(seq.rounds):
            round_num: int = round_idx + 1
            print(f"  {_B}--- 第 {round_num} 轮: {rnd.expect_phase} ---{_0}")
            print(f"  发送: {rnd.message}")

            start: float = time.monotonic()
            try:
                resp: dict[str, Any] = await call_mainagent(rnd.message, session_id=sid)
                elapsed: float = time.monotonic() - start

                text: str = resp.get("text", "")
                error: str | None = resp.get("error")

                if error:
                    print(f"  {_R}ERROR: {error}{_0}")
                    print(f"  耗时: {elapsed:.1f}s")
                    total_failed += 1
                    all_results.append((seq.name, round_num, rnd.expect_phase, False, f"error: {error[:60]}"))
                    # 继续后续轮次（不 break）
                    print()
                    continue

                # 显示回复
                preview: str = text.replace("\n", " ")[:400]
                print(f"  回复: {preview}")
                print(f"  耗时: {elapsed:.1f}s")

                # 检查 state_tree
                state_tree: str | None = read_state_tree(sid)
                if state_tree:
                    # 显示 state_tree 摘要（前 200 字）
                    st_preview: str = state_tree.replace("\n", " | ")[:200]
                    print(f"  {_Y}State Tree: {st_preview}{_0}")
                else:
                    print(f"  {_D}State Tree: (未生成){_0}")

                # 关键词检查
                hit_kws: list[str] = [kw for kw in rnd.expect_keywords if kw in text]

                if hit_kws:
                    print(f"  {_G}PASS — 命中: {', '.join(hit_kws)}{_0}")
                    total_passed += 1
                    all_results.append((seq.name, round_num, rnd.expect_phase, True, f"hit: {', '.join(hit_kws)}"))
                else:
                    print(f"  {_R}FAIL — 未命中: {rnd.expect_keywords}{_0}")
                    total_failed += 1
                    all_results.append((seq.name, round_num, rnd.expect_phase, False, f"no hit, text: {text[:80]}"))

            except Exception as e:
                elapsed = time.monotonic() - start
                print(f"  {_R}ERROR ({elapsed:.1f}s): {e}{_0}")
                total_failed += 1
                all_results.append((seq.name, round_num, rnd.expect_phase, False, str(e)[:60]))

            print()

    # 汇总
    print(f"\n{'='*70}")
    print(f"{_B}测试汇总{_0}")
    print(f"{'='*70}")
    for seq_name, round_num, phase, ok, detail in all_results:
        status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
        print(f"  [{status}] {seq_name} R{round_num} ({phase}) — {detail}")

    total: int = total_passed + total_failed
    print(f"\n总计: {total} | 通过: {total_passed} | 失败: {total_failed}")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())

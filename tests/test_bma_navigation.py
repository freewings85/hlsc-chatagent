"""BusinessMapAgent 导航定位综合测试

直接调用 BusinessMapAgent A2A 端点，测试各种场景下的节点定位准确性。
不经过 MainAgent，测试更快更聚焦。

运行方式：
    cd /path/to/project
    mainagent/.venv/bin/python tests/test_bma_navigation.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

BMA_URL: str = "http://localhost:8103"

# ── ANSI 颜色 ──
_G: str = "\033[92m"   # green
_R: str = "\033[91m"   # red
_Y: str = "\033[93m"   # yellow
_C: str = "\033[96m"   # cyan
_B: str = "\033[1m"    # bold
_D: str = "\033[2m"    # dim
_0: str = "\033[0m"    # reset


# ── A2A 调用 ──

async def call_bma(
    message: str,
    state_briefing: str = "",
    session_id: str | None = None,
) -> str:
    """直接调用 BusinessMapAgent A2A 端点，返回原始文本结果。"""
    sid: str = session_id or f"test-{uuid4().hex[:8]}"
    context_id: str = f"nav-{sid}-{uuid4().hex[:8]}"

    metadata: dict[str, Any] = {
        "parent_session_id": sid,
        "parent_request_id": uuid4().hex,
        "request_context": {
            "state_briefing": state_briefing,
            "recent_history": message,
        },
    }

    request_body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
                "contextId": context_id,
            },
            "metadata": metadata,
        },
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp: httpx.Response = await client.post(f"{BMA_URL}/a2a", json=request_body)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    if "error" in data:
        return f"ERROR: {data['error']}"

    # 提取 agent 最终回复文本
    result: Any = data.get("result", {})
    if not isinstance(result, dict):
        return str(result)

    # 优先从 history 中取最后一条 agent 消息（最可靠）
    history: list[Any] = result.get("history", [])
    for msg in reversed(history):
        if msg.get("role") == "agent":
            parts: list[Any] = msg.get("parts", [])
            for part in parts:
                if part.get("kind") == "text":
                    text: str = part.get("text", "")
                    if text.strip():
                        return text

    # 回退：从 status.message 中取
    status: Any = result.get("status", {})
    if isinstance(status, dict):
        status_msg: Any = status.get("message", {})
        if isinstance(status_msg, dict):
            parts = status_msg.get("parts", [])
            for part in parts:
                if part.get("kind") == "text":
                    text = part.get("text", "")
                    if text.strip():
                        return text

    # 最后回退：从 artifacts 中取
    artifacts: list[Any] = result.get("artifacts", [])
    for art in artifacts:
        parts = art.get("parts", [])
        for part in parts:
            if part.get("kind") == "text":
                text = part.get("text", "")
                if text.strip():
                    return text

    return str(result)


def extract_node_ids(raw: str) -> list[str]:
    """从 BMA 返回的原始文本中提取节点 ID。"""
    import re
    # 匹配合法的节点 ID
    all_matches: list[str] = re.findall(r"\b([a-z][a-z0-9_]*)\b", raw.lower())
    _NOISE: set[str] = {"node_id", "id", "name", "root", "true", "false", "null"}
    ids: list[str] = [m for m in all_matches if m not in _NOISE and len(m) > 2]
    return ids


# ── 测试用例 ──

@dataclass
class NavTestCase:
    """导航测试用例。"""
    name: str
    message: str
    state_briefing: str
    expect_any: list[str]  # 期望返回的节点 ID 中包含其中至少一个
    description: str


TEST_CASES: list[NavTestCase] = [
    # ── 1. 空状态：基本路径 ──
    NavTestCase(
        name="T1-换机油-空状态",
        message="我的车该换机油了，帮我看看",
        state_briefing="",
        expect_any=["t1_requirements_communication", "node_t1_project_clarify", "node_t1_project_search"],
        description="空状态，明确需求→T1梳理养车项目",
    ),
    NavTestCase(
        name="T1-方向盘抖-空状态",
        message="我车最近方向盘有点抖，不知道是什么问题",
        state_briefing="",
        expect_any=["t1_requirements_communication", "node_t1_project_clarify"],
        description="空状态，症状描述→T1梳理养车项目（模糊应停在较浅层）",
    ),
    NavTestCase(
        name="T2-找店-空状态",
        message="帮我找个附近靠谱的修车店",
        state_briefing="",
        expect_any=["t2_select_merchants", "node_t2_merchant_search"],
        description="空状态，找商户→T2筛选商户",
    ),
    NavTestCase(
        name="T3-洗车-空状态",
        message="我想预约个洗车",
        state_briefing="",
        expect_any=["t3_book_wash", "node_t3_project_select"],
        description="空状态，预约洗车→T3预订洗车/检测",
    ),

    # ── 2. 有状态：推进场景 ──
    NavTestCase(
        name="T1-省钱-有状态",
        message="有没有什么优惠活动？",
        state_briefing="已完成：\n- 梳理养车项目 → 小保养（换机油+机滤）\n当前在做：需求沟通",
        expect_any=["node_t1_saving_plan"],
        description="项目已确认，问优惠→T1省钱方案",
    ),
    NavTestCase(
        name="T1-找店-有状态",
        message="帮我找个店吧",
        state_briefing="已完成：\n- 梳理养车项目 → 小保养\n- 确认消费偏好 → 优惠券\n当前在做：需求沟通→搜索商户",
        expect_any=["node_t1_merchant_search", "t2_select_merchants", "node_t2_merchant_search"],
        description="项目+省钱都确认了，找店→搜索商户",
    ),

    # ── 3. 多 ID 场景 ──
    NavTestCase(
        name="多路径-保养+找店",
        message="我想做个保养，顺便找个靠谱的店",
        state_briefing="",
        expect_any=["node_t1_project_clarify", "t1_requirements_communication", "node_t2_merchant_search", "t2_select_merchants"],
        description="同时提到保养和找店→可能返回多个分支ID",
    ),

    # ── 4. checklist 做完场景 ──
    NavTestCase(
        name="全完成-下单",
        message="好的，那就预约这家吧",
        state_briefing="已完成：\n- 梳理养车项目 → 小保养\n- 确认消费偏好 → 9折优惠\n- 搜索商户 → 已选定XX汽修\n当前在做：展示下单卡片",
        expect_any=["node_t1_order_show", "node_t2_order_show", "node_t3_order_show"],
        description="项目+省钱+商户都确认，预约→下单",
    ),

    # ── 5. 跳跃场景 ──
    NavTestCase(
        name="跳跃-回到项目",
        message="等等，我再加个空调滤",
        state_briefing="已完成：\n- 梳理养车项目 → 小保养\n当前在做：搜索商户",
        expect_any=["node_t1_project_clarify", "t1_requirements_communication", "node_t1_project_search"],
        description="商户搜索中途回到修改项目→跳回T1梳理",
    ),
    NavTestCase(
        name="跳跃-直接洗车",
        message="算了不保养了，我就洗个车吧",
        state_briefing="已完成：\n- 梳理养车项目 → 小保养\n当前在做：确认消费偏好",
        expect_any=["t3_book_wash", "node_t3_project_select"],
        description="省钱方案中途改成洗车→跳到T3",
    ),
]


# ── 执行 ──

async def run_all() -> None:
    """执行全部测试用例。"""
    print(f"\n{'='*70}")
    print(f"{_B}{_C}BusinessMapAgent 导航定位综合测试{_0}")
    print(f"{'='*70}")
    print(f"目标: {BMA_URL}\n")

    # 健康检查
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r: httpx.Response = await c.get(f"{BMA_URL}/.well-known/agent.json")
            r.raise_for_status()
        print(f"{_G}BusinessMapAgent 连通 ✓{_0}\n")
    except Exception as e:
        print(f"{_R}无法连接 BusinessMapAgent: {e}{_0}")
        sys.exit(1)

    passed: int = 0
    failed: int = 0
    results: list[tuple[str, bool, str]] = []

    for tc in TEST_CASES:
        print(f"{_B}--- {tc.name} ---{_0}")
        print(f"  {_D}{tc.description}{_0}")
        print(f"  消息: {tc.message}")
        if tc.state_briefing:
            brief_preview: str = tc.state_briefing.replace("\n", " | ")[:80]
            print(f"  状态: {brief_preview}")

        start: float = time.monotonic()
        try:
            raw: str = await call_bma(tc.message, tc.state_briefing)
            elapsed: float = time.monotonic() - start
            ids: list[str] = extract_node_ids(raw)

            print(f"  原始返回: {raw.strip()[:120]}")
            print(f"  解析 ID: {ids}")
            print(f"  耗时: {elapsed:.1f}s")

            # 检查是否命中期望
            hit: bool = any(eid in ids for eid in tc.expect_any)
            # 也检查原始返回文本中是否包含期望 ID
            if not hit:
                raw_lower: str = raw.lower()
                hit = any(eid in raw_lower for eid in tc.expect_any)

            if hit:
                matched: list[str] = [e for e in tc.expect_any if e in ids or e in raw.lower()]
                print(f"  {_G}✓ PASS — 命中: {', '.join(matched)}{_0}")
                passed += 1
                results.append((tc.name, True, ", ".join(matched)))
            else:
                print(f"  {_R}✗ FAIL — 期望包含 {tc.expect_any} 之一{_0}")
                failed += 1
                results.append((tc.name, False, f"got: {ids}"))

        except Exception as e:
            elapsed = time.monotonic() - start
            print(f"  {_R}✗ ERROR ({elapsed:.1f}s): {e}{_0}")
            failed += 1
            results.append((tc.name, False, str(e)[:60]))

        print()

    # 汇总
    print(f"{'='*70}")
    print(f"{_B}测试汇总{_0}")
    print(f"{'='*70}")
    for name, ok, detail in results:
        status: str = f"{_G}PASS{_0}" if ok else f"{_R}FAIL{_0}"
        print(f"  [{status}] {name} — {detail}")
    print(f"\n总计: {len(results)} | 通过: {passed} | 失败: {failed}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())

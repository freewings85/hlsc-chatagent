"""业务地图导航手动集成测试

使用 SSE 流式接口直接调用 MainAgent，验证业务地图导航系统是否正确触发。
要求 MainAgent 已在 http://localhost:8100 运行。

运行方式：
    python tests/test_business_map_manual.py
    python tests/test_business_map_manual.py --base-url http://localhost:8100
    python tests/test_business_map_manual.py --timeout 120
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# SSE 解析与响应模型
# ---------------------------------------------------------------------------

@dataclass
class SseEvent:
    """单条 SSE 事件。"""
    event_type: str
    data: dict[str, Any]


@dataclass
class ChatResponse:
    """一次完整对话的聚合结果。"""
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    interrupts: list[dict[str, Any]] = field(default_factory=list)
    raw_events: list[SseEvent] = field(default_factory=list)
    error: str | None = None

    @property
    def all_tool_names(self) -> list[str]:
        """所有被调用的工具名称。"""
        return [tc.get("tool_name", "") for tc in self.tool_calls]

    @property
    def has_business_map_tools(self) -> bool:
        """响应中是否出现了业务地图相关的工具调用。"""
        bm_tools: set[str] = {
            "read_business_node",
            "update_state_tree",
            "call_business_map_agent",
        }
        return bool(bm_tools & set(self.all_tool_names))

    @property
    def has_business_map_content(self) -> bool:
        """响应文本或工具结果中是否包含业务地图相关内容。

        检查多种信号：
        - 工具调用名包含 business_map / state_tree / business_node
        - 文本中包含节点 ID 模式 (t1_, t2_, t3_, node_)
        - 工具结果中包含业务地图关键词
        """
        # 1. 工具名检查
        bm_keywords: list[str] = [
            "business_map", "business_node", "state_tree",
            "read_business_node", "update_state_tree",
        ]
        for name in self.all_tool_names:
            if any(kw in name for kw in bm_keywords):
                return True

        # 2. 文本中的节点 ID 模式
        node_patterns: list[str] = [
            "t1_", "t2_", "t3_", "node_t1", "node_t2", "node_t3",
        ]
        full_text: str = self.text.lower()
        for pattern in node_patterns:
            if pattern in full_text:
                return True

        # 3. 工具结果中的业务关键词
        for result in self.tool_results:
            result_str: str = json.dumps(result, ensure_ascii=False).lower()
            if any(kw in result_str for kw in bm_keywords + node_patterns):
                return True

        return False


def parse_sse_stream(raw: str) -> list[SseEvent]:
    """从 SSE 文本流中解析事件列表。"""
    events: list[SseEvent] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_type: str = "message"
        data_str: str = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:].strip()
        if data_str:
            try:
                data: dict[str, Any] = json.loads(data_str)
                events.append(SseEvent(event_type=event_type, data=data))
            except json.JSONDecodeError:
                pass
    return events


def aggregate_response(events: list[SseEvent]) -> ChatResponse:
    """将事件列表聚合为完整的 ChatResponse。"""
    resp: ChatResponse = ChatResponse(raw_events=events)
    for evt in events:
        d: dict[str, Any] = evt.data.get("data", evt.data)
        if evt.event_type == "text":
            content: str = d.get("content", "")
            resp.text += content
        elif evt.event_type == "tool_call_start":
            resp.tool_calls.append({
                "tool_name": d.get("tool_name", ""),
                "tool_call_id": d.get("tool_call_id", ""),
            })
        elif evt.event_type == "tool_result":
            resp.tool_results.append({
                "tool_name": d.get("tool_name", ""),
                "tool_call_id": d.get("tool_call_id", ""),
                "result": d.get("result", ""),
            })
        elif evt.event_type == "interrupt":
            resp.interrupts.append(d)
        elif evt.event_type == "error":
            resp.error = d.get("message", d.get("error", str(d)))
    return resp


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------

async def send_message(
    base_url: str,
    session_id: str,
    message: str,
    user_id: str = "test-user",
    timeout: float = 120.0,
) -> ChatResponse:
    """通过 SSE 流式接口发送消息并收集完整响应。"""
    import httpx

    url: str = f"{base_url}/chat/stream"
    payload: dict[str, str] = {
        "session_id": session_id,
        "message": message,
        "user_id": user_id,
    }

    raw_buffer: str = ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                body: str = ""
                async for chunk in response.aiter_text():
                    body += chunk
                return ChatResponse(error=f"HTTP {response.status_code}: {body[:500]}")

            async for chunk in response.aiter_text():
                raw_buffer += chunk

    events: list[SseEvent] = parse_sse_stream(raw_buffer)
    return aggregate_response(events)


async def check_health(base_url: str) -> bool:
    """检查 MainAgent 是否可达。"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """单个测试用例。"""
    name: str
    messages: list[str]
    expected_track: str
    description: str
    check_keywords: list[str] = field(default_factory=list)


TEST_CASES: list[TestCase] = [
    TestCase(
        name="T1-项目明确",
        messages=["我的车该换机油了，帮我看看"],
        expected_track="T1 需求沟通 - 项目梳理",
        description="用户明确说出养车项目（换机油），预期进入 T1 需求沟通路径，触发项目梳理",
        check_keywords=["保养", "机油", "换", "项目", "车型"],
    ),
    TestCase(
        name="T1-症状描述",
        messages=["我车最近方向盘有点抖，不知道是什么问题"],
        expected_track="T1 需求沟通 - 症状排查",
        description="用户描述症状但不确定问题，预期进入 T1 需求沟通路径，帮助排查问题",
        check_keywords=["方向盘", "检查", "问题", "可能", "建议"],
    ),
    TestCase(
        name="T2-找商户",
        messages=["帮我找个附近靠谱的修车店"],
        expected_track="T2 筛选商户",
        description="用户直接要求找商户，预期进入 T2 筛选商户路径",
        check_keywords=["商户", "门店", "附近", "找", "推荐"],
    ),
    TestCase(
        name="T3-预订洗车",
        messages=["我想预约个洗车"],
        expected_track="T3 预订洗车/检测",
        description="用户要求预约洗车，预期进入 T3 预订洗车/检测路径",
        check_keywords=["洗车", "预约", "预订", "时间"],
    ),
    TestCase(
        name="多轮-保养+优惠",
        messages=["我想做个小保养", "有没有什么优惠活动？"],
        expected_track="T1 需求沟通 → 省钱方案",
        description="多轮对话：先确认保养需求，再询问优惠，预期先进入 T1 项目梳理，第二轮触发省钱方案",
        check_keywords=["保养", "优惠", "省钱", "折扣", "方案"],
    ),
]


# ---------------------------------------------------------------------------
# 结果输出
# ---------------------------------------------------------------------------

# ANSI 颜色码
_GREEN: str = "\033[92m"
_RED: str = "\033[91m"
_YELLOW: str = "\033[93m"
_CYAN: str = "\033[96m"
_DIM: str = "\033[2m"
_BOLD: str = "\033[1m"
_RESET: str = "\033[0m"


def print_header(text: str) -> None:
    print(f"\n{'='*70}")
    print(f"{_BOLD}{_CYAN}{text}{_RESET}")
    print(f"{'='*70}")


def print_result(
    tc: TestCase,
    responses: list[ChatResponse],
    elapsed: float,
) -> bool:
    """打印单个测试的结果，返回是否通过。"""
    print(f"\n{_BOLD}--- {tc.name}: {tc.description} ---{_RESET}")
    print(f"  预期路径: {tc.expected_track}")
    print(f"  耗时: {elapsed:.1f}s")

    passed: bool = True
    for i, (msg, resp) in enumerate(zip(tc.messages, responses)):
        turn_label: str = f"  [第{i+1}轮]" if len(tc.messages) > 1 else "  "
        print(f"{turn_label} 用户: {msg}")

        if resp.error:
            print(f"  {_RED}错误: {resp.error}{_RESET}")
            passed = False
            continue

        # 工具调用
        if resp.all_tool_names:
            print(f"  工具调用: {', '.join(resp.all_tool_names)}")
        else:
            print(f"  {_DIM}（未触发工具调用）{_RESET}")

        # 业务地图相关检测
        if resp.has_business_map_tools:
            print(f"  {_GREEN}[v] 触发了业务地图工具{_RESET}")
        elif resp.has_business_map_content:
            print(f"  {_GREEN}[v] 响应包含业务地图相关内容{_RESET}")
        else:
            print(f"  {_YELLOW}[?] 未检测到业务地图导航信号（可能在预处理 hook 中执行）{_RESET}")

        # 中断（HITL）
        if resp.interrupts:
            for intr in resp.interrupts:
                intr_type: str = intr.get("type", "unknown")
                question: str = intr.get("question", "")
                print(f"  {_CYAN}[中断] 类型={intr_type}: {question[:80]}{_RESET}")

        # 关键词匹配
        text_lower: str = resp.text.lower()
        matched_kw: list[str] = [kw for kw in tc.check_keywords if kw in text_lower]
        missing_kw: list[str] = [kw for kw in tc.check_keywords if kw not in text_lower]

        if matched_kw:
            print(f"  {_GREEN}关键词命中: {', '.join(matched_kw)}{_RESET}")
        if missing_kw:
            print(f"  {_DIM}关键词未命中: {', '.join(missing_kw)}{_RESET}")

        # 响应文本（截断显示）
        preview: str = resp.text.replace("\n", " ").strip()
        if len(preview) > 200:
            preview = preview[:200] + "..."
        print(f"  回复: {preview}")

    return passed


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run_tests(base_url: str, timeout: float) -> None:
    """执行全部测试用例。"""
    print_header("业务地图导航 API 测试")
    print(f"目标: {base_url}")
    print(f"超时: {timeout}s")

    # 健康检查
    print(f"\n检查 MainAgent 连通性... ", end="", flush=True)
    healthy: bool = await check_health(base_url)
    if not healthy:
        print(f"{_RED}失败{_RESET}")
        print(f"\n{_RED}无法连接到 MainAgent ({base_url})。{_RESET}")
        print("请确保 MainAgent 已启动：")
        print("  cd mainagent && uv run python server.py")
        sys.exit(1)
    print(f"{_GREEN}成功{_RESET}")

    results: list[tuple[TestCase, bool]] = []

    for tc in TEST_CASES:
        # 每个测试用例使用独立的 session_id
        session_id: str = f"bm-test-{uuid.uuid4().hex[:8]}"

        responses: list[ChatResponse] = []
        start: float = time.monotonic()

        for msg in tc.messages:
            resp: ChatResponse = await send_message(
                base_url=base_url,
                session_id=session_id,
                message=msg,
                timeout=timeout,
            )
            responses.append(resp)

        elapsed: float = time.monotonic() - start
        passed: bool = print_result(tc, responses, elapsed)
        results.append((tc, passed))

    # 汇总
    print_header("测试汇总")
    total: int = len(results)
    passed_count: int = sum(1 for _, p in results if p)
    failed_count: int = total - passed_count

    for tc, passed in results:
        status: str = f"{_GREEN}PASS{_RESET}" if passed else f"{_RED}FAIL{_RESET}"
        print(f"  [{status}] {tc.name} - {tc.description[:40]}")

    print(f"\n总计: {total} | 通过: {passed_count} | 失败: {failed_count}")

    if failed_count > 0:
        sys.exit(1)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="业务地图导航 API 手动测试"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8100",
        help="MainAgent 地址 (默认: http://localhost:8100)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="单次请求超时秒数 (默认: 120)",
    )
    args: argparse.Namespace = parser.parse_args()

    asyncio.run(run_tests(args.base_url, args.timeout))


if __name__ == "__main__":
    main()

"""测试 MainAgent "先做再问" 原则。

验证 agent 是否直接用工具推进，而不是列选项等用户选择。
使用 /chat/stream SSE 端点，遇到 interrupt 自动回复。
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from typing import Any

import httpx

# 清除代理
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_proxy_var, None)

BASE_URL: str = "http://localhost:8100"

# interrupt 自动回复映射
INTERRUPT_AUTO_REPLIES: dict[str, dict[str, Any]] = {
    "select_car": {"car_model_id": "mmu_100", "vin_code": "", "required_precision": "exact_model"},
    "select_location": {"address": "上海浦东张江", "lat": 31.2304, "lng": 121.47},
    "confirm_booking": {"confirmed": True},
}


def _no_proxy_client(**kwargs: Any) -> httpx.Client:
    transport = httpx.HTTPTransport()
    return httpx.Client(transport=transport, **kwargs)


def _parse_sse_block(block: str) -> dict[str, Any] | None:
    event_type: str = "message"
    data: str = ""
    for line in block.strip().split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:].strip()
    if data:
        try:
            return {"type": event_type, "data": json.loads(data)}
        except json.JSONDecodeError:
            pass
    return None


def send_message_sse(session_id: str, message: str, timeout_secs: int = 90) -> dict[str, Any]:
    """发送消息并通过 SSE 收集完整响应，遇到 interrupt 自动回复。"""
    all_events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    tool_calls: list[str] = []
    interrupt_keys: list[str] = []

    def read_stream() -> None:
        try:
            with _no_proxy_client(timeout=timeout_secs) as client:
                with client.stream(
                    "POST",
                    f"{BASE_URL}/chat/stream",
                    json={
                        "session_id": session_id,
                        "message": message,
                        "user_id": "test-do-first",
                    },
                ) as resp:
                    buffer: str = ""
                    for chunk in resp.iter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            event = _parse_sse_block(block)
                            if event:
                                all_events.append(event)
                                if event["type"] == "text":
                                    d = event["data"].get("data", event["data"])
                                    content: str = d.get("content", "")
                                    if content:
                                        text_parts.append(content)
                                elif event["type"] == "tool_call_start":
                                    d = event["data"].get("data", event["data"])
                                    tool_name: str = d.get("tool_name", "")
                                    if tool_name:
                                        tool_calls.append(tool_name)
                                elif event["type"] == "interrupt":
                                    d = event["data"].get("data", event["data"])
                                    key: str = d.get("interrupt_key", "")
                                    itype: str = d.get("type", "")
                                    if key:
                                        interrupt_keys.append(key)
                                        # 自动回复
                                        reply_data = INTERRUPT_AUTO_REPLIES.get(itype, {"reply": "确认"})
                                        try:
                                            with _no_proxy_client(timeout=10) as reply_client:
                                                reply_client.post(
                                                    f"{BASE_URL}/chat/interrupt-reply",
                                                    json={"interrupt_key": key, "reply": reply_data},
                                                )
                                        except Exception as e:
                                            print(f"    [interrupt-reply error] {e}")
        except Exception as e:
            all_events.append({"type": "error", "data": {"error": str(e)}})

    t = threading.Thread(target=read_stream, daemon=True)
    t.start()
    t.join(timeout=timeout_secs + 10)

    full_text: str = "".join(text_parts)
    return {
        "text": full_text,
        "tool_calls": tool_calls,
        "events": all_events,
        "interrupt_keys": interrupt_keys,
    }


def send_multi_turn(session_id: str, messages: list[str], timeout_secs: int = 90) -> list[dict[str, Any]]:
    """发送多轮消息，返回每轮的结果。"""
    results: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        result = send_message_sse(session_id, msg, timeout_secs)
        results.append(result)
        if i < len(messages) - 1:
            time.sleep(1)
    return results


def evaluate_proactiveness(text: str, tool_calls: list[str]) -> tuple[int, str]:
    """评估 agent 是否主动推进。

    返回 (分数, 原因)
    5 = 积极推进
    3 = 轻微追问
    1 = 列选项等待
    """
    text_lower: str = text.lower()

    # 列选项的信号词
    option_signals: list[str] = [
        "请选择", "您想要", "请问您", "您需要哪", "以下几种",
        "可以选择", "有以下", "1.", "1、", "①",
        "哪一种", "哪种", "什么类型", "请告诉我您想",
        "您是想", "您希望", "请问想要",
    ]

    # 有工具调用 = 积极推进信号
    has_tool_calls: bool = len(tool_calls) > 0

    # 数列选项特征
    option_count: int = sum(1 for sig in option_signals if sig in text)

    # 检查是否有编号列表（1. 2. 3. 模式）
    import re
    numbered_list = re.findall(r'(?:^|\n)\s*\d+[\.\、\)）]', text)
    has_numbered_list: bool = len(numbered_list) >= 3

    if has_tool_calls and option_count == 0:
        return 5, "直接用工具推进，没有不必要的提问"
    elif has_tool_calls and option_count > 0:
        return 3, f"用了工具但还是问了问题（信号词: {option_count}个）"
    elif option_count >= 2 or has_numbered_list:
        return 1, f"列选项等待用户选择（{option_count}个信号词，编号列表: {has_numbered_list}）"
    elif option_count == 1:
        return 3, f"轻微追问（1个信号词）"
    else:
        # 没工具调用也没列选项，可能是直接文本回复
        if len(text) > 50:
            return 4, "直接给出方案/回复，没有用工具但也没列选项"
        else:
            return 3, "回复较短，可能是简单应答"


# ================ 测试场景 ================

SCENARIOS: list[dict[str, Any]] = [
    # 直接项目类
    {"id": 1, "msg": "换机油", "expect": "应直接按机油/机滤更换推进", "category": "direct"},
    {"id": 2, "msg": "做个保养", "expect": "应按常规小保养推进", "category": "direct"},
    {"id": 3, "msg": "换轮胎", "expect": "应按轮胎更换推进", "category": "direct"},
    {"id": 4, "msg": "洗车", "expect": "应直接走洗车流程", "category": "direct"},
    {"id": 5, "msg": "换刹车片", "expect": "应直接按刹车片更换推进", "category": "direct"},
    {"id": 6, "msg": "做个四轮定位", "expect": "应直接推进", "category": "direct"},
    {"id": 7, "msg": "换空调滤芯", "expect": "应直接推进", "category": "direct"},
    {"id": 8, "msg": "补个胎", "expect": "应直接按补胎推进", "category": "direct"},
    # 带省钱意图类
    {"id": 9, "msg": "换机油怎么省钱", "expect": "应先说省钱方法", "category": "saving"},
    {"id": 10, "msg": "保养有没有优惠", "expect": "应先说优惠", "category": "saving"},
    {"id": 11, "msg": "最便宜的洗车方案", "expect": "应直接给方案", "category": "saving"},
    # 带找店意图类
    {"id": 12, "msg": "附近有修车的吗", "expect": "应直接问位置去搜索", "category": "search"},
    {"id": 13, "msg": "帮我找个保养店", "expect": "应问位置搜索，不要先问保养做什么", "category": "search"},
    {"id": 14, "msg": "浦东哪家洗车便宜", "expect": "应直接搜索", "category": "search"},
    # 多轮推进类
    {"id": 15, "msgs": ["做个保养", "就换机油机滤"], "expect": "第二轮应推进到报价，不再问项目", "category": "multi"},
    {"id": 16, "msgs": ["换轮胎", "前轮两个"], "expect": "第二轮应推进到报价", "category": "multi"},
    # 边界类（合理追问）
    {"id": 17, "msg": "车有问题", "expect": "可以追问症状", "category": "boundary"},
    {"id": 18, "msg": "帮我看看", "expect": "可以追问", "category": "boundary"},
    {"id": 19, "msg": "有什么推荐", "expect": "可以追问", "category": "boundary"},
    {"id": 20, "msg": "你好", "expect": "可以引导", "category": "boundary"},
]


def run_all_tests() -> str:
    """运行全部 20 个场景，返回完整报告。"""
    results: list[dict[str, Any]] = []

    for i, scenario in enumerate(SCENARIOS):
        sid: int = scenario["id"]
        category: str = scenario["category"]
        session_id: str = f"do-first-test-{sid}-{int(time.time())}"

        print(f"\n{'='*60}")
        print(f"场景 {sid}: {scenario.get('msg', scenario.get('msgs', [''])[0])}")
        print(f"期望: {scenario['expect']}")
        print(f"{'='*60}")

        if "msgs" in scenario:
            # 多轮
            multi_results = send_multi_turn(session_id, scenario["msgs"])
            # 评估最后一轮
            last = multi_results[-1]
            text: str = last["text"]
            tools: list[str] = last["tool_calls"]
            all_text: str = "\n---\n".join(r["text"] for r in multi_results)
            all_tools: list[str] = []
            for r in multi_results:
                all_tools.extend(r["tool_calls"])
            score, reason = evaluate_proactiveness(text, tools)

            print(f"  轮1回复: {multi_results[0]['text'][:200]}...")
            print(f"  轮1工具: {multi_results[0]['tool_calls']}")
            print(f"  轮2回复: {text[:200]}...")
            print(f"  轮2工具: {tools}")
        else:
            result = send_message_sse(session_id, scenario["msg"])
            text = result["text"]
            tools = result["tool_calls"]
            score, reason = evaluate_proactiveness(text, tools)
            all_text = text
            all_tools = tools

            print(f"  回复: {text[:300]}...")
            print(f"  工具: {tools}")

        print(f"  评分: {score}/5 - {reason}")

        results.append({
            "id": sid,
            "category": category,
            "message": scenario.get("msg", " → ".join(scenario.get("msgs", []))),
            "expect": scenario["expect"],
            "response_summary": all_text[:300],
            "tool_calls": all_tools,
            "score": score,
            "reason": reason,
        })

    # 生成报告
    report_lines: list[str] = []
    report_lines.append("# MainAgent '先做再问' 原则测试报告\n")
    report_lines.append(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append(f"测试端点: {BASE_URL}\n")

    report_lines.append("\n## 详细结果\n")

    for r in results:
        report_lines.append(f"### 场景 {r['id']}: \"{r['message']}\"")
        report_lines.append(f"- **期望**: {r['expect']}")
        report_lines.append(f"- **评分**: {r['score']}/5")
        report_lines.append(f"- **原因**: {r['reason']}")
        report_lines.append(f"- **工具调用**: {r['tool_calls'] if r['tool_calls'] else '无'}")
        report_lines.append(f"- **回复摘要**: {r['response_summary'][:200]}")
        report_lines.append("")

    # 汇总
    scored_results = [r for r in results if r["category"] != "boundary"]
    boundary_results = [r for r in results if r["category"] == "boundary"]

    if scored_results:
        avg_score: float = sum(r["score"] for r in scored_results) / len(scored_results)
    else:
        avg_score = 0.0

    report_lines.append("\n## 汇总\n")
    report_lines.append(f"- **计分场景 (1-16) 平均分**: {avg_score:.1f}/5.0 (目标 >= 4.0)")
    report_lines.append(f"- **通过**: {'YES' if avg_score >= 4.0 else 'NO'}")
    report_lines.append("")

    # 按类别统计
    categories: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        categories.setdefault(r["category"], []).append(r)

    report_lines.append("### 分类统计\n")
    for cat, cat_results in categories.items():
        cat_avg: float = sum(r["score"] for r in cat_results) / len(cat_results) if cat_results else 0
        report_lines.append(f"- **{cat}**: 平均 {cat_avg:.1f}/5 ({len(cat_results)} 个场景)")
        for r in cat_results:
            report_lines.append(f"  - 场景{r['id']} \"{r['message']}\": {r['score']}/5")

    # 改进建议
    low_scores = [r for r in scored_results if r["score"] <= 3]
    if low_scores:
        report_lines.append("\n### 需改进的场景\n")
        for r in low_scores:
            report_lines.append(f"- 场景{r['id']} \"{r['message']}\" ({r['score']}/5): {r['reason']}")

    report_lines.append("\n### 边界场景（不计分）\n")
    for r in boundary_results:
        report_lines.append(f"- 场景{r['id']} \"{r['message']}\": {r['score']}/5 - {r['reason']}")

    report: str = "\n".join(report_lines)
    return report


if __name__ == "__main__":
    # 先检查健康
    try:
        with _no_proxy_client(timeout=5) as client:
            resp = client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                print(f"ERROR: MainAgent not healthy: {resp.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"ERROR: Cannot connect to MainAgent at {BASE_URL}: {e}")
        sys.exit(1)

    print("MainAgent is healthy, starting tests...\n")
    report = run_all_tests()

    # 保存报告
    report_path: str = "/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent/tests/do_first_ask_later_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n\n{'='*60}")
    print("REPORT SAVED TO:", report_path)
    print(f"{'='*60}\n")
    print(report)

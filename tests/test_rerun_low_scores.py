"""重跑得分低的 8 个场景，验证改进效果。

场景: 2(做个保养), 3(换轮胎), 4(洗车), 5(换刹车片), 8(补个胎), 9(换机油怎么省钱), 10(保养有没有优惠), 15(做个保养→就换机油机滤)
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


def send_message_sse(session_id: str, message: str, timeout_secs: int = 120) -> dict[str, Any]:
    all_events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    tool_calls: list[str] = []

    def read_stream() -> None:
        try:
            with _no_proxy_client(timeout=timeout_secs) as client:
                with client.stream(
                    "POST",
                    f"{BASE_URL}/chat/stream",
                    json={
                        "session_id": session_id,
                        "message": message,
                        "user_id": "test-rerun",
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
                                        reply_data = INTERRUPT_AUTO_REPLIES.get(itype, {"reply": "确认"})
                                        try:
                                            with _no_proxy_client(timeout=10) as rc:
                                                rc.post(
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

    return {
        "text": "".join(text_parts),
        "tool_calls": tool_calls,
        "events": all_events,
    }


# 场景定义
RERUN_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": 2, "msg": "做个保养",
        "expect": "应直接按常规小保养（机油/机滤更换）推进",
        "old_score": 3, "old_issue": "问燃油养护还是制动养护二选一",
    },
    {
        "id": 3, "msg": "换轮胎",
        "expect": "应直接按轮胎更换推进，不列补胎/换位等",
        "old_score": 1, "old_issue": "列了4种（轮胎更换、换位、补胎、轮毂翻新）",
    },
    {
        "id": 4, "msg": "洗车",
        "expect": "应直接按基础洗车推进",
        "old_score": 1, "old_issue": "列了5种洗车让用户选",
    },
    {
        "id": 5, "msg": "换刹车片",
        "expect": "应问前/后（合理），但不列刹车盘等无关项",
        "old_score": 3, "old_issue": "列了6项含刹车盘和驻车制动片",
    },
    {
        "id": 8, "msg": "补个胎",
        "expect": "应直接按胶条补胎推进",
        "old_score": 1, "old_issue": "列了3种补胎方式让用户选",
    },
    {
        "id": 9, "msg": "换机油怎么省钱",
        "expect": "应直接给省钱方案或直接查价",
        "old_score": 3, "old_issue": "反问要不要查而不是直接查",
    },
    {
        "id": 10, "msg": "保养有没有优惠",
        "expect": "应直接按小保养查优惠",
        "old_score": 3, "old_issue": "反问要不要按小保养查",
    },
    {
        "id": 15, "msgs": ["做个保养", "就换机油机滤"],
        "expect": "第二轮应直接推进到报价，不再列其他选项",
        "old_score": 3, "old_issue": "用户说就换机油机滤还列了空气滤芯等选项",
    },
]


def main() -> None:
    # 健康检查
    try:
        with _no_proxy_client(timeout=5) as client:
            resp = client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                print(f"ERROR: MainAgent not healthy: {resp.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"ERROR: Cannot connect to MainAgent: {e}")
        sys.exit(1)

    print("MainAgent healthy. Re-running 8 low-scoring scenarios...\n")

    results: list[dict[str, Any]] = []

    for scenario in RERUN_SCENARIOS:
        sid: int = scenario["id"]
        ts: int = int(time.time())
        session_id: str = f"rerun-{sid}-{ts}"

        print(f"\n{'='*60}")
        print(f"场景 {sid}: {scenario.get('msg', scenario.get('msgs', [''])[0])}")
        print(f"期望: {scenario['expect']}")
        print(f"上次: {scenario['old_score']}/5 - {scenario['old_issue']}")
        print(f"{'='*60}")

        if "msgs" in scenario:
            # 多轮
            all_text_parts: list[str] = []
            all_tools: list[str] = []
            for i, msg in enumerate(scenario["msgs"]):
                r = send_message_sse(session_id, msg)
                all_text_parts.append(f"[轮{i+1}] {r['text']}")
                all_tools.extend(r["tool_calls"])
                print(f"  轮{i+1}回复: {r['text'][:300]}")
                print(f"  轮{i+1}工具: {r['tool_calls']}")
                if i < len(scenario["msgs"]) - 1:
                    time.sleep(1)
            full_text: str = "\n".join(all_text_parts)
            tool_calls: list[str] = all_tools
        else:
            r = send_message_sse(session_id, scenario["msg"])
            full_text = r["text"]
            tool_calls = r["tool_calls"]
            print(f"  回复: {full_text[:400]}")
            print(f"  工具: {tool_calls}")

        results.append({
            "id": sid,
            "msg": scenario.get("msg", " → ".join(scenario.get("msgs", []))),
            "expect": scenario["expect"],
            "old_score": scenario["old_score"],
            "old_issue": scenario["old_issue"],
            "text": full_text,
            "tool_calls": tool_calls,
        })

    # 输出对比报告
    print(f"\n\n{'='*60}")
    print("RE-TEST COMPLETE - SUMMARY")
    print(f"{'='*60}\n")

    for r in results:
        print(f"场景 {r['id']}: \"{r['msg']}\"")
        print(f"  上次: {r['old_score']}/5 ({r['old_issue']})")
        print(f"  工具: {r['tool_calls']}")
        print(f"  回复: {r['text'][:300]}")
        print()

    # 保存
    report_path: str = "/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent/tests/rerun_low_scores_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Raw results saved to: {report_path}")


if __name__ == "__main__":
    main()

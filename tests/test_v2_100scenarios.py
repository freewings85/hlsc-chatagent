"""养车省钱助手 100 场景端到端测试

通过 POST /chat/stream SSE 端点调用 MainAgent，自动处理 interrupt，
验证 100 个场景下的回复质量。

运行方式：
    cd mainagent && .venv/bin/python ../tests/test_v2_100scenarios.py

可选参数：
    --category A          只跑某个分类（A/B/C/D/E/F）
    --range 1-20          只跑某个 ID 范围
    --timeout 180         单轮超时（秒，默认 120）
    --base-url http://..  MainAgent 地址（默认 http://localhost:8100）
    --output report.txt   报告输出路径（默认 stdout + tests/scenario-report.txt）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

# ── 默认配置 ──
DEFAULT_BASE_URL: str = "http://localhost:8100"
DEFAULT_TIMEOUT: int = 120

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
class Scenario:
    """单个测试场景定义。"""
    id: int
    category: str
    name: str
    messages: list[str]
    expect_keywords: list[str]
    expect_no_keywords: list[str]
    expect_behavior: str


@dataclass
class RoundResult:
    """单轮对话结果。"""
    round_num: int
    user_message: str
    response_text: str
    tool_calls: list[str]
    interrupts: list[dict[str, Any]]
    elapsed_seconds: float
    error: str = ""


@dataclass
class ScenarioResult:
    """单个场景的完整评估结果。"""
    scenario: Scenario
    rounds: list[RoundResult]
    keyword_hits: list[str]
    keyword_misses: list[str]
    forbidden_hits: list[str]
    has_off_topic: bool
    guides_saving: bool
    all_within_timeout: bool
    passed: bool
    notes: list[str] = field(default_factory=list)


# ============================================================
# Interrupt 自动回复映射
# ============================================================

INTERRUPT_AUTO_REPLIES: dict[str, dict[str, Any]] = {
    "select_car": {
        "car_model_id": "mmu_100",
        "car_model_name": "2021款大众朗逸 1.5L 自动舒适版",
        "vin_code": "",
        "required_precision": "exact_model",
    },
    "select_location": {
        "address": "上海浦东张江",
        "lat": 31.2304,
        "lng": 121.47,
    },
    "confirm_booking": {
        "confirmed": True,
        "user_msg": "确认预订",
    },
}


# ============================================================
# SSE 流式客户端
# ============================================================


async def _send_interrupt_reply(
    client: httpx.AsyncClient,
    base_url: str,
    interrupt_key: str,
    interrupt_type: str,
) -> str | None:
    """发送 interrupt-reply，返回错误信息或 None。"""
    reply_data: dict[str, Any] = INTERRUPT_AUTO_REPLIES.get(
        interrupt_type,
        {"reply": "ok"},
    )
    try:
        reply_resp: httpx.Response = await client.post(
            f"{base_url}/chat/interrupt-reply",
            json={
                "interrupt_key": interrupt_key,
                "reply": reply_data,
            },
        )
        if reply_resp.status_code == 410:
            return "interrupt 已失效（服务重启）"
    except Exception as e:
        return f"interrupt-reply 失败: {e}"
    return None


async def chat_stream_with_interrupt(
    base_url: str,
    session_id: str,
    message: str,
    user_id: str,
    timeout: int,
) -> RoundResult:
    """调用 /chat/stream SSE 端点，自动处理 interrupt，返回完整结果。

    关键设计：interrupt 发生时，agent 在服务端阻塞等待 resume，SSE 连接保持打开。
    我们需要在**不断开 SSE 连接**的情况下并发发送 interrupt-reply，
    这样 agent 解除阻塞后继续产出的事件仍能通过同一个 SSE 流接收到。
    """
    start: float = time.monotonic()
    text_parts: list[str] = []
    tool_calls: list[str] = []
    interrupts: list[dict[str, Any]] = []
    error: str = ""

    try:
        # 使用单个 client 实例：SSE 流 + interrupt-reply 共享
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(timeout))) as client:
            request_body: dict[str, Any] = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
            }
            async with client.stream(
                "POST",
                f"{base_url}/chat/stream",
                json=request_body,
            ) as resp:
                resp.raise_for_status()
                buffer: str = ""

                async for chunk in resp.aiter_text():
                    buffer += chunk
                    # 解析 SSE 事件
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
                            data: dict[str, Any] = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        evt_data: dict[str, Any] = data.get("data", {})

                        if event_type == "text":
                            content: str = evt_data.get("content", "")
                            if content:
                                text_parts.append(content)

                        elif event_type == "tool_call_start":
                            tool_name: str = evt_data.get("tool_name", "unknown")
                            tool_calls.append(tool_name)

                        elif event_type == "interrupt":
                            i_key: str = evt_data.get("interrupt_key", "")
                            i_type: str = evt_data.get("type", "")
                            interrupts.append({
                                "type": i_type,
                                "interrupt_key": i_key,
                                "question": evt_data.get("question", ""),
                            })
                            # 并发发送 interrupt-reply，不断开 SSE 流。
                            # agent 在服务端阻塞等待 resume；resume 后
                            # 后续事件继续通过同一个 SSE 连接推送。
                            if i_key and i_type:
                                reply_err: str | None = await _send_interrupt_reply(
                                    client, base_url, i_key, i_type,
                                )
                                if reply_err:
                                    error = reply_err

                        elif event_type == "error":
                            err_msg: str = evt_data.get("message", evt_data.get("error", str(evt_data)))
                            error = err_msg

                        elif event_type == "chat_request_end":
                            pass  # SSE 流即将正常结束

    except httpx.ReadTimeout:
        error = f"超时（{timeout}s）"
    except httpx.ConnectError as e:
        error = f"连接失败: {e}"
    except Exception as e:
        error = str(e)

    elapsed: float = time.monotonic() - start

    return RoundResult(
        round_num=0,  # 调用方设置
        user_message=message,
        response_text="".join(text_parts),
        tool_calls=tool_calls,
        interrupts=interrupts,
        elapsed_seconds=elapsed,
        error=error,
    )


# ============================================================
# 场景评估
# ============================================================


# 闲聊/发散指标：回复中出现这些词且当前场景不相关时算发散
OFF_TOPIC_MARKERS: list[str] = [
    "作为AI", "作为一个AI", "我是一个语言模型", "很抱歉我无法",
    "抱歉，我不能", "我没有情感", "对不起，作为",
]

# 省钱引导关键词
SAVING_KEYWORDS: list[str] = [
    "省钱", "优惠", "折扣", "九折", "划算", "便宜", "省", "活动",
    "券", "打折", "满减", "返现", "补贴", "特价", "促销",
]


def evaluate_scenario(
    scenario: Scenario,
    rounds: list[RoundResult],
    single_round_timeout: int,
) -> ScenarioResult:
    """评估一个场景的所有轮次结果。"""
    # 合并所有轮次的回复文本
    all_text: str = " ".join(r.response_text for r in rounds)

    # 关键词命中
    keyword_hits: list[str] = [kw for kw in scenario.expect_keywords if kw in all_text]
    keyword_misses: list[str] = [kw for kw in scenario.expect_keywords if kw not in all_text]

    # 禁止关键词
    forbidden_hits: list[str] = [kw for kw in scenario.expect_no_keywords if kw in all_text]

    # 闲聊发散（仅对非闲聊场景检测）
    has_off_topic: bool = False
    if scenario.category not in ("E",):
        has_off_topic = any(marker in all_text for marker in OFF_TOPIC_MARKERS)

    # 是否主动引导省钱（对 B 类场景特别关注）
    guides_saving: bool = any(kw in all_text for kw in SAVING_KEYWORDS)

    # 响应时间
    all_within_timeout: bool = all(r.elapsed_seconds < single_round_timeout for r in rounds)

    # 是否有错误
    has_error: bool = any(bool(r.error) for r in rounds)

    notes: list[str] = []
    if has_error:
        error_msgs: list[str] = [r.error for r in rounds if r.error]
        notes.append(f"错误: {'; '.join(error_msgs)}")

    # 通过判定：至少命中一个关键词 + 无禁止词 + 无发散 + 无错误
    passed: bool = (
        len(keyword_hits) > 0
        and len(forbidden_hits) == 0
        and not has_off_topic
        and not has_error
    )

    return ScenarioResult(
        scenario=scenario,
        rounds=rounds,
        keyword_hits=keyword_hits,
        keyword_misses=keyword_misses,
        forbidden_hits=forbidden_hits,
        has_off_topic=has_off_topic,
        guides_saving=guides_saving,
        all_within_timeout=all_within_timeout,
        passed=passed,
        notes=notes,
    )


# ============================================================
# 100 个场景定义
# ============================================================


def define_scenarios() -> list[Scenario]:
    """定义 100 个测试场景。"""
    scenarios: list[Scenario] = []

    # ── A. 项目确认类（20 个）──

    # A1-5: 直接表达项目
    scenarios.append(Scenario(
        id=1, category="A", name="直接表达-换机油",
        messages=["我要换机油"],
        expect_keywords=["机油", "车型", "车辆", "保养"],
        expect_no_keywords=[],
        expect_behavior="识别换机油意图，询问车型或确认项目",
    ))
    scenarios.append(Scenario(
        id=2, category="A", name="直接表达-换轮胎",
        messages=["我想换轮胎"],
        expect_keywords=["轮胎", "车型", "尺寸", "车辆", "规格", "型号"],
        expect_no_keywords=[],
        expect_behavior="识别换轮胎意图，询问车型或轮胎规格",
    ))
    scenarios.append(Scenario(
        id=3, category="A", name="直接表达-做保养",
        messages=["我车要做保养了"],
        expect_keywords=["保养", "车型", "车辆", "机油", "项目", "公里"],
        expect_no_keywords=[],
        expect_behavior="识别保养意图，询问车型或里程等信息",
    ))
    scenarios.append(Scenario(
        id=4, category="A", name="直接表达-洗车",
        messages=["我想洗车"],
        expect_keywords=["洗车", "门店", "店", "时间", "预约", "什么时候"],
        expect_no_keywords=[],
        expect_behavior="识别洗车意图，引导门店或时间选择",
    ))
    scenarios.append(Scenario(
        id=5, category="A", name="直接表达-换刹车片",
        messages=["要换刹车片"],
        expect_keywords=["刹车片", "车型", "车辆", "制动", "前", "后"],
        expect_no_keywords=[],
        expect_behavior="识别换刹车片意图，询问车型或前后位置",
    ))

    # A6-10: 模糊意图
    scenarios.append(Scenario(
        id=6, category="A", name="模糊意图-该保养了",
        messages=["感觉该保养了"],
        expect_keywords=["保养", "车型", "公里", "多久", "上次", "里程", "车辆"],
        expect_no_keywords=[],
        expect_behavior="引导用户明确保养需求，询问里程等",
    ))
    scenarios.append(Scenario(
        id=7, category="A", name="模糊意图-车有问题",
        messages=["我的车好像有点问题"],
        expect_keywords=["什么", "问题", "症状", "具体", "情况", "表现", "哪里"],
        expect_no_keywords=[],
        expect_behavior="引导用户描述具体问题",
    ))
    scenarios.append(Scenario(
        id=8, category="A", name="模糊意图-想检查下",
        messages=["想检查一下车子"],
        expect_keywords=["检查", "检测", "车辆", "项目", "哪些", "车型", "全车"],
        expect_no_keywords=[],
        expect_behavior="询问具体要检查什么",
    ))
    scenarios.append(Scenario(
        id=9, category="A", name="模糊意图-跑了3万公里",
        messages=["我的车跑了3万公里了"],
        expect_keywords=["保养", "万公里", "项目", "更换", "检查", "建议", "车型"],
        expect_no_keywords=[],
        expect_behavior="基于里程推荐保养项目",
    ))
    scenarios.append(Scenario(
        id=10, category="A", name="模糊意图-车开了两年",
        messages=["这车已经开了两年了"],
        expect_keywords=["保养", "检查", "两年", "建议", "项目", "车型", "里程"],
        expect_no_keywords=[],
        expect_behavior="基于车龄引导保养需求",
    ))

    # A11-15: 症状描述
    scenarios.append(Scenario(
        id=11, category="A", name="症状-刹车异响",
        messages=["刹车的时候有异响"],
        expect_keywords=["刹车", "异响", "检查", "刹车片", "车型", "制动", "磨损"],
        expect_no_keywords=[],
        expect_behavior="识别刹车异响症状，建议检查刹车片",
    ))
    scenarios.append(Scenario(
        id=12, category="A", name="症状-方向盘抖",
        messages=["方向盘在高速的时候会抖"],
        expect_keywords=["方向盘", "抖", "四轮定位", "动平衡", "轮胎", "检查", "车型"],
        expect_no_keywords=[],
        expect_behavior="识别方向盘抖动，建议轮胎或底盘检查",
    ))
    scenarios.append(Scenario(
        id=13, category="A", name="症状-启动困难",
        messages=["最近启动的时候不太好打火"],
        expect_keywords=["启动", "电瓶", "蓄电池", "火花塞", "检查", "车型", "打火"],
        expect_no_keywords=[],
        expect_behavior="识别启动困难，建议检查电瓶或点火系统",
    ))
    scenarios.append(Scenario(
        id=14, category="A", name="症状-空调不凉",
        messages=["空调开了不凉怎么回事"],
        expect_keywords=["空调", "制冷", "冷媒", "检查", "加氟", "滤芯", "车型"],
        expect_no_keywords=[],
        expect_behavior="识别空调问题，建议检查制冷系统",
    ))
    scenarios.append(Scenario(
        id=15, category="A", name="症状-油耗高",
        messages=["油耗好高啊最近"],
        expect_keywords=["油耗", "高", "保养", "检查", "火花塞", "滤芯", "车型", "里程"],
        expect_no_keywords=[],
        expect_behavior="识别油耗偏高，建议排查原因",
    ))

    # A16-20: 多项目同时提
    scenarios.append(Scenario(
        id=16, category="A", name="多项目-换机油顺便洗车",
        messages=["换机油的时候顺便洗个车"],
        expect_keywords=["机油", "洗车", "车型", "项目"],
        expect_no_keywords=[],
        expect_behavior="识别两个项目：换机油+洗车",
    ))
    scenarios.append(Scenario(
        id=17, category="A", name="多项目-保养加检测",
        messages=["做个保养再做个全车检测"],
        expect_keywords=["保养", "检测", "车型", "项目"],
        expect_no_keywords=[],
        expect_behavior="识别保养+全车检测两个项目",
    ))
    scenarios.append(Scenario(
        id=18, category="A", name="多项目-换轮胎做定位",
        messages=["换轮胎顺便做个四轮定位"],
        expect_keywords=["轮胎", "四轮定位", "车型"],
        expect_no_keywords=[],
        expect_behavior="识别换轮胎+四轮定位",
    ))
    scenarios.append(Scenario(
        id=19, category="A", name="多项目-机油机滤空滤",
        messages=["换机油、机滤和空气滤芯"],
        expect_keywords=["机油", "机滤", "空气滤", "车型", "保养"],
        expect_no_keywords=[],
        expect_behavior="识别三个项目",
    ))
    scenarios.append(Scenario(
        id=20, category="A", name="多项目-大保养套餐",
        messages=["想做个大保养，该换的都换一下"],
        expect_keywords=["大保养", "车型", "项目", "机油", "公里", "里程"],
        expect_no_keywords=[],
        expect_behavior="确认大保养内容",
    ))

    # ── B. 省钱导向类（20 个）──

    # B21-25: 直接问省钱
    scenarios.append(Scenario(
        id=21, category="B", name="省钱-有没有优惠",
        messages=["保养有没有什么优惠"],
        expect_keywords=["优惠", "折扣", "活动", "省钱", "券", "划算", "省"],
        expect_no_keywords=[],
        expect_behavior="介绍优惠活动或省钱方案",
    ))
    scenarios.append(Scenario(
        id=22, category="B", name="省钱-怎么省钱",
        messages=["换机油怎么才能省钱"],
        expect_keywords=["省钱", "优惠", "便宜", "划算", "省", "方案", "折扣"],
        expect_no_keywords=[],
        expect_behavior="给出省钱建议",
    ))
    scenarios.append(Scenario(
        id=23, category="B", name="省钱-有折扣吗",
        messages=["你们有折扣吗"],
        expect_keywords=["折扣", "优惠", "活动", "九折", "券", "省"],
        expect_no_keywords=[],
        expect_behavior="介绍折扣信息",
    ))
    scenarios.append(Scenario(
        id=24, category="B", name="省钱-最便宜的方案",
        messages=["有没有最便宜的保养方案"],
        expect_keywords=["便宜", "省钱", "价格", "方案", "优惠", "划算"],
        expect_no_keywords=[],
        expect_behavior="推荐性价比最高的方案",
    ))
    scenarios.append(Scenario(
        id=25, category="B", name="省钱-能打折吗",
        messages=["保养能打折吗"],
        expect_keywords=["打折", "折扣", "优惠", "省", "活动"],
        expect_no_keywords=[],
        expect_behavior="说明折扣情况",
    ))

    # B26-30: 价格敏感
    scenarios.append(Scenario(
        id=26, category="B", name="价格敏感-太贵了",
        messages=["换机油要500块太贵了吧"],
        expect_keywords=["价格", "便宜", "划算", "省", "方案", "优惠", "选择", "其他"],
        expect_no_keywords=[],
        expect_behavior="理解价格敏感，提供更经济的选择",
    ))
    scenarios.append(Scenario(
        id=27, category="B", name="价格敏感-便宜点",
        messages=["能不能便宜点"],
        expect_keywords=["价格", "优惠", "便宜", "方案", "省", "券"],
        expect_no_keywords=[],
        expect_behavior="提供降价方案",
    ))
    scenarios.append(Scenario(
        id=28, category="B", name="价格敏感-预算有限",
        messages=["我预算有限，保养预算300以内"],
        expect_keywords=["预算", "方案", "价格", "推荐", "省", "300", "便宜"],
        expect_no_keywords=[],
        expect_behavior="在预算范围内推荐方案",
    ))
    scenarios.append(Scenario(
        id=29, category="B", name="价格敏感-更划算的",
        messages=["有没有更划算的做法"],
        expect_keywords=["划算", "省钱", "方案", "优惠", "便宜", "建议"],
        expect_no_keywords=[],
        expect_behavior="推荐更划算的方式",
    ))
    scenarios.append(Scenario(
        id=30, category="B", name="价格敏感-比外面贵",
        messages=["你们这个比外面修理厂贵啊"],
        expect_keywords=["价格", "对比", "优惠", "省", "品质", "保障", "服务"],
        expect_no_keywords=[],
        expect_behavior="说明平台优势或提供优惠",
    ))

    # B31-35: 比价类
    scenarios.append(Scenario(
        id=31, category="B", name="比价-行情价",
        messages=["小保养一般行情价多少"],
        expect_keywords=["价格", "行情", "费用", "一般", "大概", "左右", "元"],
        expect_no_keywords=[],
        expect_behavior="给出行情价参考",
    ))
    scenarios.append(Scenario(
        id=32, category="B", name="比价-别家多少钱",
        messages=["换轮胎别家多少钱"],
        expect_keywords=["价格", "对比", "不同", "商户", "店", "费用"],
        expect_no_keywords=[],
        expect_behavior="提供价格对比信息",
    ))
    scenarios.append(Scenario(
        id=33, category="B", name="比价-和4S店比",
        messages=["你们和4S店比怎么样"],
        expect_keywords=["4S", "价格", "对比", "优势", "服务", "省", "便宜"],
        expect_no_keywords=[],
        expect_behavior="与4S店对比",
    ))
    scenarios.append(Scenario(
        id=34, category="B", name="比价-线上线下",
        messages=["在你们这做和去外面做差多少"],
        expect_keywords=["价格", "差", "对比", "优惠", "优势", "省"],
        expect_no_keywords=[],
        expect_behavior="对比平台与线下价格差异",
    ))
    scenarios.append(Scenario(
        id=35, category="B", name="比价-同项目不同店",
        messages=["同样的保养项目不同店差价大吗"],
        expect_keywords=["价格", "差", "不同", "店", "商户", "对比", "报价"],
        expect_no_keywords=[],
        expect_behavior="说明不同店铺价格差异",
    ))

    # B36-40: 优惠券相关
    scenarios.append(Scenario(
        id=36, category="B", name="优惠券-有什么券",
        messages=["有什么优惠券可以用吗"],
        expect_keywords=["券", "优惠", "使用", "领", "活动", "折扣"],
        expect_no_keywords=[],
        expect_behavior="介绍可用优惠券",
    ))
    scenarios.append(Scenario(
        id=37, category="B", name="优惠券-九折怎么用",
        messages=["九折券怎么用"],
        expect_keywords=["九折", "券", "使用", "下单", "优惠", "折扣"],
        expect_no_keywords=[],
        expect_behavior="说明九折券使用方式",
    ))
    scenarios.append(Scenario(
        id=38, category="B", name="优惠券-能叠加吗",
        messages=["优惠券能叠加使用吗"],
        expect_keywords=["叠加", "券", "使用", "优惠", "规则"],
        expect_no_keywords=[],
        expect_behavior="说明叠加规则",
    ))
    scenarios.append(Scenario(
        id=39, category="B", name="优惠券-券在哪领",
        messages=["优惠券在哪领"],
        expect_keywords=["券", "领", "获取", "页面", "活动", "入口"],
        expect_no_keywords=[],
        expect_behavior="引导领券路径",
    ))
    scenarios.append(Scenario(
        id=40, category="B", name="优惠券-优惠力度",
        messages=["你们平台优惠力度大吗"],
        expect_keywords=["优惠", "力度", "省", "折扣", "活动", "划算"],
        expect_no_keywords=[],
        expect_behavior="说明优惠力度",
    ))

    # ── C. 商户相关类（15 个）──

    # C41-45: 找店
    scenarios.append(Scenario(
        id=41, category="C", name="找店-附近有什么店",
        messages=["附近有什么汽修店"],
        expect_keywords=["位置", "附近", "店", "商户", "推荐", "搜索", "地址"],
        expect_no_keywords=[],
        expect_behavior="询问位置或搜索附近门店",
    ))
    scenarios.append(Scenario(
        id=42, category="C", name="找店-推荐靠谱的",
        messages=["推荐个靠谱的保养店"],
        expect_keywords=["推荐", "店", "商户", "位置", "评价", "口碑"],
        expect_no_keywords=[],
        expect_behavior="推荐高评价门店",
    ))
    scenarios.append(Scenario(
        id=43, category="C", name="找店-最近的",
        messages=["离我最近的修车店在哪"],
        expect_keywords=["位置", "最近", "店", "距离", "附近", "地址"],
        expect_no_keywords=[],
        expect_behavior="询问位置然后推荐最近门店",
    ))
    scenarios.append(Scenario(
        id=44, category="C", name="找店-指定区域",
        messages=["浦东有什么好的汽修店"],
        expect_keywords=["浦东", "店", "商户", "推荐", "位置"],
        expect_no_keywords=[],
        expect_behavior="在浦东区域搜索门店",
    ))
    scenarios.append(Scenario(
        id=45, category="C", name="找店-能修什么",
        messages=["附近有什么能做维修的店"],
        expect_keywords=["维修", "店", "位置", "商户", "附近"],
        expect_no_keywords=[],
        expect_behavior="搜索提供维修服务的门店",
    ))

    # C46-50: 商户偏好
    scenarios.append(Scenario(
        id=46, category="C", name="商户偏好-要4S店",
        messages=["我只去4S店"],
        expect_keywords=["4S", "店", "品牌", "车型"],
        expect_no_keywords=[],
        expect_behavior="筛选4S店",
    ))
    scenarios.append(Scenario(
        id=47, category="C", name="商户偏好-连锁品牌",
        messages=["有没有连锁品牌的店"],
        expect_keywords=["连锁", "品牌", "店", "推荐", "途虎", "商户"],
        expect_no_keywords=[],
        expect_behavior="推荐连锁品牌门店",
    ))
    scenarios.append(Scenario(
        id=48, category="C", name="商户偏好-上次那家",
        messages=["我想去上次去的那家店"],
        expect_keywords=["上次", "去过", "历史", "记录", "店"],
        expect_no_keywords=[],
        expect_behavior="查询历史去过的门店",
    ))
    scenarios.append(Scenario(
        id=49, category="C", name="商户偏好-评价好的",
        messages=["给我推荐评价好的店"],
        expect_keywords=["评价", "口碑", "推荐", "店", "好评", "商户"],
        expect_no_keywords=[],
        expect_behavior="按评价推荐门店",
    ))
    scenarios.append(Scenario(
        id=50, category="C", name="商户偏好-技术好的",
        messages=["要技术好的师傅"],
        expect_keywords=["技术", "师傅", "店", "专业", "推荐", "经验"],
        expect_no_keywords=[],
        expect_behavior="推荐技术过硬的门店",
    ))

    # C51-55: 商户+项目组合
    scenarios.append(Scenario(
        id=51, category="C", name="商户项目-变速箱油",
        messages=["哪家店能做变速箱油更换"],
        expect_keywords=["变速箱油", "店", "商户", "更换", "位置"],
        expect_no_keywords=[],
        expect_behavior="搜索能做变速箱油的门店",
    ))
    scenarios.append(Scenario(
        id=52, category="C", name="商户项目-洗车便宜",
        messages=["哪家洗车最便宜"],
        expect_keywords=["洗车", "便宜", "价格", "店", "推荐"],
        expect_no_keywords=[],
        expect_behavior="推荐价格低的洗车店",
    ))
    scenarios.append(Scenario(
        id=53, category="C", name="商户项目-钣喷",
        messages=["附近有能做钣金喷漆的店吗"],
        expect_keywords=["钣金", "喷漆", "钣喷", "店", "位置", "商户"],
        expect_no_keywords=[],
        expect_behavior="搜索钣喷门店",
    ))
    scenarios.append(Scenario(
        id=54, category="C", name="商户项目-空调维修",
        messages=["哪里可以修空调"],
        expect_keywords=["空调", "维修", "店", "位置", "检查"],
        expect_no_keywords=[],
        expect_behavior="推荐空调维修门店",
    ))
    scenarios.append(Scenario(
        id=55, category="C", name="商户项目-轮胎有好店吗",
        messages=["换轮胎去哪家店好"],
        expect_keywords=["轮胎", "店", "推荐", "位置", "商户"],
        expect_no_keywords=[],
        expect_behavior="推荐换轮胎门店",
    ))

    # ── D. 预订下单类（15 个）──

    # D56-60: 直接预订
    scenarios.append(Scenario(
        id=56, category="D", name="直接预订-帮我预订",
        messages=["帮我预订保养"],
        expect_keywords=["预订", "预约", "车型", "项目", "时间", "确认"],
        expect_no_keywords=[],
        expect_behavior="启动预订流程，确认必要信息",
    ))
    scenarios.append(Scenario(
        id=57, category="D", name="直接预订-约明天下午",
        messages=["帮我约个明天下午的保养"],
        expect_keywords=["明天", "下午", "预约", "预订", "车型", "项目"],
        expect_no_keywords=[],
        expect_behavior="确认明天下午预约，收集信息",
    ))
    scenarios.append(Scenario(
        id=58, category="D", name="直接预订-周末有空",
        messages=["这周末想去做个保养"],
        expect_keywords=["周末", "预约", "保养", "车型", "时间"],
        expect_no_keywords=[],
        expect_behavior="安排周末保养预约",
    ))
    scenarios.append(Scenario(
        id=59, category="D", name="直接预订-马上能去吗",
        messages=["现在就想去保养，马上能去吗"],
        expect_keywords=["今天", "现在", "预约", "时间", "门店", "车型", "马上"],
        expect_no_keywords=[],
        expect_behavior="确认当前可用性",
    ))
    scenarios.append(Scenario(
        id=60, category="D", name="直接预订-在线下单",
        messages=["我想在线下个保养的单"],
        expect_keywords=["下单", "预订", "项目", "车型", "确认"],
        expect_no_keywords=[],
        expect_behavior="引导在线下单流程",
    ))

    # D61-65: 预订+省钱
    scenarios.append(Scenario(
        id=61, category="D", name="预订省钱-用九折",
        messages=["用九折券帮我预订保养"],
        expect_keywords=["九折", "预订", "保养", "车型", "优惠"],
        expect_no_keywords=[],
        expect_behavior="用九折券下单保养",
    ))
    scenarios.append(Scenario(
        id=62, category="D", name="预订省钱-最便宜方式",
        messages=["用最便宜的方式帮我预订小保养"],
        expect_keywords=["便宜", "省", "预订", "保养", "方案", "价格"],
        expect_no_keywords=[],
        expect_behavior="推荐最经济方案并预订",
    ))
    scenarios.append(Scenario(
        id=63, category="D", name="预订省钱-划算下单",
        messages=["帮我找个划算的方案下单"],
        expect_keywords=["划算", "方案", "下单", "省", "优惠"],
        expect_no_keywords=[],
        expect_behavior="推荐划算方案下单",
    ))
    scenarios.append(Scenario(
        id=64, category="D", name="预订省钱-有优惠再下单",
        messages=["有优惠活动的话帮我下单"],
        expect_keywords=["优惠", "活动", "下单", "预订"],
        expect_no_keywords=[],
        expect_behavior="介绍优惠后引导下单",
    ))
    scenarios.append(Scenario(
        id=65, category="D", name="预订省钱-便宜店预订",
        messages=["帮我找个便宜的店预订保养"],
        expect_keywords=["便宜", "店", "预订", "保养", "价格", "推荐"],
        expect_no_keywords=[],
        expect_behavior="推荐低价门店并预订",
    ))

    # D66-70: 改主意
    scenarios.append(Scenario(
        id=66, category="D", name="改主意-不做了",
        messages=["算了不做保养了"],
        expect_keywords=["好的", "了解", "没关系", "需要", "随时", "可以", "帮"],
        expect_no_keywords=[],
        expect_behavior="尊重用户决定，提供后续帮助",
    ))
    scenarios.append(Scenario(
        id=67, category="D", name="改主意-换个项目",
        messages=["不做保养了，帮我洗个车吧"],
        expect_keywords=["洗车", "好的", "了解", "门店", "预约", "时间"],
        expect_no_keywords=[],
        expect_behavior="切换到洗车流程",
    ))
    scenarios.append(Scenario(
        id=68, category="D", name="改主意-换家店",
        messages=["这家店不行，换一家"],
        expect_keywords=["换", "店", "其他", "推荐", "商户", "别的"],
        expect_no_keywords=[],
        expect_behavior="推荐其他门店",
    ))
    scenarios.append(Scenario(
        id=69, category="D", name="改主意-改时间",
        messages=["时间改到下周吧"],
        expect_keywords=["下周", "时间", "改", "预约", "安排"],
        expect_no_keywords=[],
        expect_behavior="修改预约时间",
    ))
    scenarios.append(Scenario(
        id=70, category="D", name="改主意-再想想",
        messages=["我再想想吧"],
        expect_keywords=["好的", "了解", "随时", "可以", "帮", "需要", "欢迎"],
        expect_no_keywords=[],
        expect_behavior="尊重用户考虑，保持可用性",
    ))

    # ── E. 闲聊/边界类（15 个）──

    # E71-75: 闲聊
    scenarios.append(Scenario(
        id=71, category="E", name="闲聊-你好",
        messages=["你好"],
        expect_keywords=["你好", "您好", "嗨", "欢迎", "帮", "养车", "服务"],
        expect_no_keywords=[],
        expect_behavior="礼貌回应，引导到业务",
    ))
    scenarios.append(Scenario(
        id=72, category="E", name="闲聊-谢谢",
        messages=["谢谢你的帮助"],
        expect_keywords=["不客气", "客气", "帮", "需要", "随时", "谢"],
        expect_no_keywords=[],
        expect_behavior="礼貌回应",
    ))
    scenarios.append(Scenario(
        id=73, category="E", name="闲聊-再见",
        messages=["好了谢谢再见"],
        expect_keywords=["再见", "拜拜", "祝", "随时", "欢迎", "帮", "下次"],
        expect_no_keywords=[],
        expect_behavior="礼貌道别",
    ))
    scenarios.append(Scenario(
        id=74, category="E", name="闲聊-天气",
        messages=["今天天气不错"],
        expect_keywords=["养车", "帮", "车", "服务", "需要", "保养", "项目"],
        expect_no_keywords=[],
        expect_behavior="简短回应后引导回业务",
    ))
    scenarios.append(Scenario(
        id=75, category="E", name="闲聊-你是机器人吗",
        messages=["你是机器人吗"],
        expect_keywords=["助手", "AI", "帮", "养车", "服务", "智能", "是"],
        expect_no_keywords=[],
        expect_behavior="说明身份，引导到业务",
    ))

    # E76-80: 平台相关
    scenarios.append(Scenario(
        id=76, category="E", name="平台-你是谁",
        messages=["你是谁？能做什么？"],
        expect_keywords=["养车", "助手", "帮", "省钱", "保养", "服务"],
        expect_no_keywords=[],
        expect_behavior="自我介绍和能力说明",
    ))
    scenarios.append(Scenario(
        id=77, category="E", name="平台-能做什么",
        messages=["你能帮我做什么"],
        expect_keywords=["保养", "养车", "省钱", "预约", "帮", "服务"],
        expect_no_keywords=[],
        expect_behavior="列举可提供的服务",
    ))
    scenarios.append(Scenario(
        id=78, category="E", name="平台-话痨是什么",
        messages=["话痨是什么"],
        expect_keywords=["话痨", "平台", "助手", "帮", "功能", "养车"],
        expect_no_keywords=[],
        expect_behavior="解释平台/助手概念",
    ))
    scenarios.append(Scenario(
        id=79, category="E", name="平台-九折啥意思",
        messages=["九折是啥意思"],
        expect_keywords=["九折", "折扣", "优惠", "10%", "90%", "价格"],
        expect_no_keywords=[],
        expect_behavior="解释九折含义",
    ))
    scenarios.append(Scenario(
        id=80, category="E", name="平台-怎么使用",
        messages=["怎么用你们平台"],
        expect_keywords=["使用", "平台", "保养", "预约", "步骤", "帮", "告诉"],
        expect_no_keywords=[],
        expect_behavior="介绍使用流程",
    ))

    # E81-85: 超出能力
    scenarios.append(Scenario(
        id=81, category="E", name="超能力-买保险",
        messages=["帮我买个车险"],
        expect_keywords=["养车", "保养", "维修", "服务", "保险", "帮", "范围"],
        expect_no_keywords=[],
        expect_behavior="说明不支持保险业务，引导回养车",
    ))
    scenarios.append(Scenario(
        id=82, category="E", name="超能力-二手车估价",
        messages=["我的车能值多少钱"],
        expect_keywords=["养车", "保养", "估价", "服务", "范围", "帮"],
        expect_no_keywords=[],
        expect_behavior="说明不支持估价，引导回养车",
    ))
    scenarios.append(Scenario(
        id=83, category="E", name="超能力-驾照",
        messages=["怎么考驾照"],
        expect_keywords=["养车", "保养", "驾照", "服务", "帮", "范围"],
        expect_no_keywords=[],
        expect_behavior="说明不在服务范围内",
    ))
    scenarios.append(Scenario(
        id=84, category="E", name="超能力-违章查询",
        messages=["帮我查下有没有违章"],
        expect_keywords=["违章", "养车", "保养", "服务", "帮", "范围", "查"],
        expect_no_keywords=[],
        expect_behavior="说明不支持违章查询",
    ))
    scenarios.append(Scenario(
        id=85, category="E", name="超能力-贷款",
        messages=["有没有车贷优惠"],
        expect_keywords=["养车", "保养", "贷款", "服务", "帮", "范围"],
        expect_no_keywords=[],
        expect_behavior="说明不支持贷款业务",
    ))

    # ── F. 多轮深度流程（15 个）──

    # F86-90: 完整流程
    scenarios.append(Scenario(
        id=86, category="F", name="完整流程-保养到下单",
        messages=[
            "我车该保养了",
            "就换个机油和机滤吧，小保养",
            "有什么优惠吗",
            "帮我找个店吧",
        ],
        expect_keywords=["保养", "机油", "车型"],
        expect_no_keywords=[],
        expect_behavior="从项目确认到省钱方案到找店的完整流程",
    ))
    scenarios.append(Scenario(
        id=87, category="F", name="完整流程-轮胎到预订",
        messages=[
            "轮胎该换了",
            "四条都换",
            "帮我找个便宜的店",
        ],
        expect_keywords=["轮胎", "车型"],
        expect_no_keywords=[],
        expect_behavior="从换轮胎到找店的流程",
    ))
    scenarios.append(Scenario(
        id=88, category="F", name="完整流程-症状到检查",
        messages=[
            "刹车有异响",
            "高速刹车的时候比较明显",
            "那帮我检查一下吧",
        ],
        expect_keywords=["刹车", "检查", "异响"],
        expect_no_keywords=[],
        expect_behavior="从症状描述到安排检查",
    ))
    scenarios.append(Scenario(
        id=89, category="F", name="完整流程-模糊到明确",
        messages=[
            "车好像有点问题",
            "开着方向盘会抖",
            "那需要做什么",
            "好的帮我安排",
        ],
        expect_keywords=["方向盘", "检查"],
        expect_no_keywords=[],
        expect_behavior="从模糊描述到明确项目到安排",
    ))
    scenarios.append(Scenario(
        id=90, category="F", name="完整流程-省钱导向完整",
        messages=[
            "想保养但是想省钱",
            "有什么优惠活动",
            "用优惠帮我预订",
        ],
        expect_keywords=["保养", "省钱", "优惠"],
        expect_no_keywords=[],
        expect_behavior="以省钱为核心的完整流程",
    ))

    # F91-95: 中途改主意流程
    scenarios.append(Scenario(
        id=91, category="F", name="改主意流程-项目切换",
        messages=[
            "我想做个大保养",
            "太贵了算了，就做个小保养吧",
        ],
        expect_keywords=["保养", "小保养"],
        expect_no_keywords=[],
        expect_behavior="从大保养切换到小保养",
    ))
    scenarios.append(Scenario(
        id=92, category="F", name="改主意流程-放弃再回来",
        messages=[
            "帮我保养",
            "算了不做了",
            "还是做吧，帮我安排",
        ],
        expect_keywords=["保养", "好的"],
        expect_no_keywords=[],
        expect_behavior="放弃后重新回到保养流程",
    ))
    scenarios.append(Scenario(
        id=93, category="F", name="改主意流程-换商户",
        messages=[
            "帮我找个保养的店",
            "这家太远了换一家",
        ],
        expect_keywords=["店", "推荐", "其他"],
        expect_no_keywords=[],
        expect_behavior="更换推荐门店",
    ))
    scenarios.append(Scenario(
        id=94, category="F", name="改主意流程-加项目",
        messages=[
            "换机油",
            "顺便也换个空气滤芯吧",
        ],
        expect_keywords=["机油", "空气滤"],
        expect_no_keywords=[],
        expect_behavior="在原有项目上追加新项目",
    ))
    scenarios.append(Scenario(
        id=95, category="F", name="改主意流程-减项目",
        messages=[
            "做个大保养",
            "刹车油先不换了",
        ],
        expect_keywords=["保养", "好的", "了解", "刹车油"],
        expect_no_keywords=[],
        expect_behavior="从大保养中去掉部分项目",
    ))

    # F96-100: 复杂场景
    scenarios.append(Scenario(
        id=96, category="F", name="复杂-多问题同时",
        messages=["保养多少钱，顺便问下你们有洗车吗，还有轮胎能换吗"],
        expect_keywords=["保养", "洗车", "轮胎"],
        expect_no_keywords=[],
        expect_behavior="同时回应多个问题",
    ))
    scenarios.append(Scenario(
        id=97, category="F", name="复杂-信息不全",
        messages=[
            "帮我预订保养",
            "什么车不重要吧直接预订",
        ],
        expect_keywords=["车型", "车辆", "需要", "确认"],
        expect_no_keywords=[],
        expect_behavior="坚持收集必要信息",
    ))
    scenarios.append(Scenario(
        id=98, category="F", name="复杂-犹豫纠结",
        messages=[
            "想保养但是不确定该不该做",
            "你觉得有必要吗",
            "那再等等吧",
        ],
        expect_keywords=["保养", "建议"],
        expect_no_keywords=[],
        expect_behavior="给出专业建议，尊重用户决定",
    ))
    scenarios.append(Scenario(
        id=99, category="F", name="复杂-情绪表达",
        messages=[
            "4S店报价太坑了气死我了",
            "你们能便宜多少",
        ],
        expect_keywords=["价格", "优惠", "省", "便宜", "理解"],
        expect_no_keywords=[],
        expect_behavior="共情理解后引导省钱",
    ))
    scenarios.append(Scenario(
        id=100, category="F", name="复杂-老用户回访",
        messages=[
            "上次在你们这做的保养挺好的",
            "这次想做个大保养",
        ],
        expect_keywords=["大保养", "车型", "项目"],
        expect_no_keywords=[],
        expect_behavior="延续良好体验，引导大保养",
    ))

    return scenarios


# ============================================================
# 运行引擎
# ============================================================


async def run_scenario(
    scenario: Scenario,
    base_url: str,
    timeout: int,
) -> ScenarioResult:
    """运行单个场景的所有轮次。"""
    session_id: str = f"test-v2-{scenario.id:03d}-{uuid4().hex[:6]}"
    user_id: str = "test-user-v2"

    rounds: list[RoundResult] = []

    for idx, message in enumerate(scenario.messages):
        result: RoundResult = await chat_stream_with_interrupt(
            base_url=base_url,
            session_id=session_id,
            message=message,
            user_id=user_id,
            timeout=timeout,
        )
        result.round_num = idx + 1
        rounds.append(result)

        # 如果出错，继续后续轮次（记录错误但不中断）
        if result.error:
            pass

    return evaluate_scenario(scenario, rounds, timeout)


async def run_all(
    scenarios: list[Scenario],
    base_url: str,
    timeout: int,
    output_path: str | None,
) -> None:
    """运行所有场景并输出报告。"""
    print(f"\n{'='*70}")
    print(f"{_B}{_C}养车省钱助手 100 场景端到端测试{_0}")
    print(f"{'='*70}")
    print(f"目标: {base_url}")
    print(f"场景数: {len(scenarios)}")
    print(f"单轮超时: {timeout}s\n")

    # 健康检查
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r: httpx.Response = await c.get(f"{base_url}/health")
            r.raise_for_status()
        print(f"{_G}MainAgent 连通{_0}\n")
    except Exception as e:
        print(f"{_R}无法连接 MainAgent ({base_url}): {e}{_0}")
        print("请确保 MainAgent 已启动。")
        sys.exit(1)

    results: list[ScenarioResult] = []
    category_stats: dict[str, dict[str, int]] = {}
    start_time: float = time.monotonic()

    for i, scenario in enumerate(scenarios):
        cat: str = scenario.category
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "pass": 0, "fail": 0}

        print(f"  [{i+1}/{len(scenarios)}] #{scenario.id:03d} [{cat}] {scenario.name} ...", end=" ", flush=True)

        result: ScenarioResult = await run_scenario(scenario, base_url, timeout)
        results.append(result)

        category_stats[cat]["total"] += 1
        if result.passed:
            category_stats[cat]["pass"] += 1
            print(f"{_G}PASS{_0} ({result.rounds[-1].elapsed_seconds:.1f}s)")
        else:
            category_stats[cat]["fail"] += 1
            reason: str = ""
            if result.notes:
                reason = result.notes[0]
            elif result.forbidden_hits:
                reason = f"禁止词: {result.forbidden_hits}"
            elif result.has_off_topic:
                reason = "闲聊发散"
            elif not result.keyword_hits:
                preview: str = result.rounds[-1].response_text[:80].replace("\n", " ")
                reason = f"关键词未命中, 回复: {preview}"
            print(f"{_R}FAIL{_0} ({result.rounds[-1].elapsed_seconds:.1f}s) — {reason}")

        # 显示关键词命中详情（仅失败时）
        if not result.passed and result.keyword_misses:
            print(f"       期望: {scenario.expect_keywords}")
            print(f"       命中: {result.keyword_hits}")
            print(f"       未中: {result.keyword_misses}")

    total_elapsed: float = time.monotonic() - start_time

    # ── 汇总报告 ──
    report_lines: list[str] = []
    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("汇总报告")
    report_lines.append("=" * 70)

    total: int = len(results)
    passed: int = sum(1 for r in results if r.passed)
    failed: int = total - passed
    pass_rate: float = passed / max(total, 1) * 100

    report_lines.append(f"总场景数:    {total}")
    report_lines.append(f"通过:        {passed} ({pass_rate:.1f}%)")
    report_lines.append(f"失败:        {failed}")
    report_lines.append(f"总耗时:      {total_elapsed:.1f}s")
    report_lines.append(f"平均耗时:    {total_elapsed / max(total, 1):.1f}s/场景")
    report_lines.append("")

    # 按分类统计
    category_names: dict[str, str] = {
        "A": "项目确认类",
        "B": "省钱导向类",
        "C": "商户相关类",
        "D": "预订下单类",
        "E": "闲聊/边界类",
        "F": "多轮深度流程",
    }
    report_lines.append("按分类统计:")
    for cat in sorted(category_stats.keys()):
        stats: dict[str, int] = category_stats[cat]
        cat_name: str = category_names.get(cat, cat)
        cat_rate: float = stats["pass"] / max(stats["total"], 1) * 100
        report_lines.append(
            f"  [{cat}] {cat_name:10s}: "
            f"{stats['pass']}/{stats['total']} 通过 ({cat_rate:.0f}%)"
        )
    report_lines.append("")

    # 省钱引导统计
    saving_total: int = sum(1 for r in results if r.scenario.category in ("A", "B", "D", "F"))
    saving_guided: int = sum(1 for r in results if r.guides_saving and r.scenario.category in ("A", "B", "D", "F"))
    report_lines.append(f"省钱引导率:  {saving_guided}/{saving_total} "
                        f"({saving_guided / max(saving_total, 1) * 100:.0f}%)")

    # 响应时间统计
    all_round_times: list[float] = [
        rr.elapsed_seconds for r in results for rr in r.rounds
    ]
    if all_round_times:
        avg_time: float = sum(all_round_times) / len(all_round_times)
        max_time: float = max(all_round_times)
        timeout_count: int = sum(1 for t in all_round_times if t >= timeout)
        report_lines.append(f"平均响应时间: {avg_time:.1f}s")
        report_lines.append(f"最大响应时间: {max_time:.1f}s")
        report_lines.append(f"超时次数:     {timeout_count}")
    report_lines.append("")

    # 失败详情
    failed_results: list[ScenarioResult] = [r for r in results if not r.passed]
    if failed_results:
        report_lines.append("失败场景详情:")
        report_lines.append("-" * 50)
        for r in failed_results:
            report_lines.append(f"  #{r.scenario.id:03d} [{r.scenario.category}] {r.scenario.name}")
            report_lines.append(f"    预期行为: {r.scenario.expect_behavior}")
            report_lines.append(f"    命中/总数: {len(r.keyword_hits)}/{len(r.scenario.expect_keywords)}")
            if r.forbidden_hits:
                report_lines.append(f"    禁止词命中: {r.forbidden_hits}")
            if r.has_off_topic:
                report_lines.append(f"    闲聊发散: 是")
            if r.notes:
                report_lines.append(f"    备注: {'; '.join(r.notes)}")
            # 显示最后一轮的回复摘要
            last_round: RoundResult = r.rounds[-1]
            preview_text: str = last_round.response_text.replace("\n", " ")[:200]
            report_lines.append(f"    回复: {preview_text}")
            if last_round.tool_calls:
                report_lines.append(f"    工具: {last_round.tool_calls}")
            if last_round.interrupts:
                int_types: list[str] = [i["type"] for i in last_round.interrupts]
                report_lines.append(f"    中断: {int_types}")
            report_lines.append("")

    # 输出报告
    report_text: str = "\n".join(report_lines)
    print(report_text)

    # 保存报告
    if output_path:
        save_path: Path = Path(output_path)
    else:
        save_path = Path(__file__).parent / "scenario-report.txt"
    save_path.write_text(report_text, encoding="utf-8")
    print(f"\n报告已保存到: {save_path}")

    # 返回退出码
    if failed > 0:
        sys.exit(1)


# ============================================================
# 入口
# ============================================================


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="养车省钱助手 100 场景端到端测试",
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="只跑某个分类（A/B/C/D/E/F）",
    )
    parser.add_argument(
        "--range", type=str, default=None, dest="id_range",
        help="只跑某个 ID 范围（如 1-20）",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"单轮超时时间（秒，默认 {DEFAULT_TIMEOUT}）",
    )
    parser.add_argument(
        "--base-url", type=str, default=DEFAULT_BASE_URL,
        help=f"MainAgent 地址（默认 {DEFAULT_BASE_URL}）",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="报告输出路径",
    )
    return parser.parse_args()


def main() -> None:
    """主入口。"""
    args: argparse.Namespace = parse_args()

    all_scenarios: list[Scenario] = define_scenarios()

    # 过滤
    filtered: list[Scenario] = all_scenarios

    if args.category:
        cat_upper: str = args.category.upper()
        filtered = [s for s in filtered if s.category == cat_upper]
        if not filtered:
            print(f"分类 '{args.category}' 没有匹配的场景。可用分类: A B C D E F")
            sys.exit(1)

    if args.id_range:
        try:
            parts: list[str] = args.id_range.split("-")
            range_start: int = int(parts[0])
            range_end: int = int(parts[1]) if len(parts) > 1 else range_start
            filtered = [s for s in filtered if range_start <= s.id <= range_end]
        except (ValueError, IndexError):
            print(f"无效的范围格式: '{args.id_range}'，应为 '1-20' 或 '5'")
            sys.exit(1)
        if not filtered:
            print(f"范围 {args.id_range} 没有匹配的场景")
            sys.exit(1)

    asyncio.run(run_all(
        scenarios=filtered,
        base_url=args.base_url,
        timeout=args.timeout,
        output_path=args.output,
    ))


if __name__ == "__main__":
    main()

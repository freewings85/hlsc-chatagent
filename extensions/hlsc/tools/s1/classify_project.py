"""classify_project 工具：粗粒度项目分类，将用户描述归到项目大类。

S1 专属，不调外部 API，直接基于关键词匹配到预定义的项目大类。
用于 S1 漏斗中"弄清项目"阶段，为后续展示省钱方法提供项目类型。
"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("classify_project")


# ============================================================
# 项目大类定义
# ============================================================

_PROJECT_MAP: list[dict[str, str | list[str]]] = [
    {
        "project_id": "maintenance",
        "project_name": "保养",
        "keywords": ["保养", "机油", "机滤", "小保养", "大保养", "换机油"],
    },
    {
        "project_id": "tire",
        "project_name": "轮胎更换",
        "keywords": ["轮胎", "换胎", "补胎", "四轮定位", "动平衡"],
    },
    {
        "project_id": "brake",
        "project_name": "刹车片更换",
        "keywords": ["刹车", "刹车片", "刹车盘", "制动"],
    },
    {
        "project_id": "body_paint",
        "project_name": "钣喷",
        "keywords": ["钣喷", "喷漆", "补漆", "钣金", "划痕", "凹陷"],
    },
    {
        "project_id": "wash",
        "project_name": "洗车美容",
        "keywords": ["洗车", "打蜡", "抛光", "镀晶", "贴膜", "美容"],
    },
    {
        "project_id": "inspection",
        "project_name": "检测",
        "keywords": ["检测", "年检", "年审", "检查", "二手车检测"],
    },
    {
        "project_id": "9999",
        "project_name": "保险项目",
        "keywords": ["保险", "出险", "理赔", "走保险", "报案"],
    },
    {
        "project_id": "repair",
        "project_name": "维修",
        "keywords": ["维修", "修车", "修理", "故障", "异响", "抖动", "漏油", "冒烟"],
    },
    {
        "project_id": "battery",
        "project_name": "电瓶蓄电池",
        "keywords": ["电瓶", "蓄电池", "搭电", "打不着火"],
    },
    {
        "project_id": "ac",
        "project_name": "空调",
        "keywords": ["空调", "制冷", "加氟", "冷媒", "空调滤芯"],
    },
]


def _classify(project_name_keyword: str) -> dict[str, str | list[dict[str, str]]]:
    """根据关键词匹配项目，可能返回多个。"""
    kw: str = project_name_keyword.strip()
    matched: list[dict[str, str]] = []
    for proj in _PROJECT_MAP:
        keywords: list[str] = proj["keywords"]  # type: ignore[assignment]
        keyword: str
        for keyword in keywords:
            if keyword in kw:
                matched.append({
                    "project_id": str(proj["project_id"]),
                    "project_name": str(proj["project_name"]),
                })
                break
    return {
        "project_name_keyword": project_name_keyword,
        "projects": matched,
    }


async def classify_project(
    ctx: RunContext[AgentDeps],
    project_name_keyword: Annotated[str, Field(description="用户提到的养车项目名称关键词，如'换机油'、'轮胎'、'保养'、'走保险'")],
) -> str:
    """粗粒度项目分类，将用户描述归到项目大类。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("classify_project", sid, rid, {"project_name_keyword": project_name_keyword})

    result: dict[str, str | list[dict[str, str]]] = _classify(project_name_keyword)
    result_json: str = json.dumps(result, ensure_ascii=False)

    projects: list[dict[str, str]] = result.get("projects", [])  # type: ignore[assignment]
    log_tool_end("classify_project", sid, rid, {
        "matched": [p["project_name"] for p in projects],
    })
    return result_json


classify_project.__doc__ = _DESCRIPTION

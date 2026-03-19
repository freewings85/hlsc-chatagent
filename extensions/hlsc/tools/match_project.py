"""match_project 工具：将关键词匹配为系统中的养车服务项目。"""

from __future__ import annotations

import json
import os
from typing import Annotated

import httpx
from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
SEARCH_PROJECT_PATH: str = "/service_ai_datamanager/project/searchProjectPackageByKeyword"

_DESCRIPTION: str = load_tool_prompt("match_project")


async def match_project(
    ctx: RunContext[AgentDeps],
    keyword: Annotated[str, Field(description="项目关键词，如'洗车'、'四轮定位'、'保养'")],
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("match_project", sid, rid, {"keyword": keyword})

    try:
        if not DATA_MANAGER_URL:
            return "Error: DATA_MANAGER_URL 未配置"

        url: str = f"{DATA_MANAGER_URL}{SEARCH_PROJECT_PATH}"
        payload: dict = {
            "searchKey": keyword,
            "top_k": 10,
            "similarity_threshold": 0.3,
            "vector_similarity_weight": 0.3,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            resp_data: dict = response.json()

        if resp_data.get("status") != 0:
            return f"Error: {resp_data.get('message', '未知错误')}"

        raw_list: list[dict] = resp_data.get("result") or []
        projects: list[dict] = [
            {
                "project_id": item.get("packageId", 0),
                "name": item.get("packageName", ""),
            }
            for item in raw_list
        ]

        data: dict = {"keyword": keyword, "projects": projects}
        result_json: str = json.dumps(data, ensure_ascii=False)

        # 业务提示
        if projects:
            names: str = "、".join(p["name"] for p in projects)
            notice: str = f"\n[业务提示] 匹配到项目：{names}"
        else:
            notice = f"\n[业务提示] 「{keyword}」未匹配到相关项目"

        log_tool_end("match_project", sid, rid, {
            "matched": [p["name"] for p in projects],
        })

        return result_json + notice

    except Exception as e:
        log_tool_end("match_project", sid, rid, exc=e)
        return f"Error: match_project failed - {e}"


match_project.__doc__ = _DESCRIPTION

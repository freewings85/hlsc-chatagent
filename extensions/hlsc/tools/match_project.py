"""match_project 工具：将关键词匹配为系统中的养车服务项目。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.car_project_retrieval_service import car_project_retrieval_service
from hlsc.services.restful.get_project_bycar_service import get_project_ids_by_car
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("match_project")


async def match_project(
    ctx: RunContext[AgentDeps],
    keyword: Annotated[str, Field(description="项目关键词，如'洗车'、'四轮定位'、'保养'")],
    car_model_id: Annotated[str, Field(description="车型编码")],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("match_project", sid, rid, {"keyword": keyword, "car_model_id": car_model_id})

    try:
        # 1. 获取车型项目清单（用于过滤）
        primary_project_ids = await get_project_ids_by_car(car_model_id, sid, rid)

        # 2. 检索项目
        result = await car_project_retrieval_service.retrieval(
            keyword,
            session_id=sid,
            request_id=rid,
            primary_project_ids=primary_project_ids or None,
        )

        # 3. 构建返回结果
        data = {"keyword": keyword, "projects": {}}
        if result.exact:
            data["projects"]["exact"] = [
                {"project_id": p.project_id, "name": p.project_name} for p in result.exact
            ]
        if result.fuzzy:
            data["projects"]["fuzzy"] = [
                {"project_id": p.project_id, "name": p.project_name} for p in result.fuzzy
            ]

        result_json = json.dumps(data, ensure_ascii=False)

        # 4. 业务提示
        notices = []
        if result.exact:
            names = "、".join(p.project_name for p in result.exact)
            notices.append(f"精确匹配到项目「{names}」")
        elif result.fuzzy:
            notices.append("未精确匹配到项目，以下是模糊候选")
        else:
            notices.append(f"「{keyword}」未匹配到相关项目")

        notice = "\n[业务提示] " + "。".join(notices)

        log_tool_end("match_project", sid, rid, {
            "exact": [p.project_name for p in result.exact],
            "fuzzy": [p.project_name for p in result.fuzzy],
        })

        return result_json + notice

    except Exception as e:
        log_tool_end("match_project", sid, rid, exc=e)
        return f"Error: match_project failed - {e}"


match_project.__doc__ = _DESCRIPTION

"""classify_project 工具：粗粒度项目分类，将用户描述归到项目大类。

调用 DataManager 的 searchPackageByKeyword 接口，将关键词匹配到项目大类。
保险类关键词特殊处理，直接返回保险项目，不调 API。
"""

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
SEARCH_PACKAGE_PATH: str = "/service_ai_datamanager/package/searchPackageByKeyword"

_DESCRIPTION: str = load_tool_prompt("classify_project")

# 保险类关键词，命中时直接返回保险项目，不调 API
_INSURANCE_KEYWORDS: list[str] = ["保险", "出险", "理赔", "走保险", "报案"]


async def classify_project(
    ctx: RunContext[AgentDeps],
    project_name_keyword: Annotated[str, Field(description="用户提到的养车项目名称关键词，如'换机油'、'轮胎'、'保养'、'走保险'")],
) -> str:
    """粗粒度项目分类，将用户描述归到项目大类。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    keyword: str = project_name_keyword.strip()
    log_tool_start("classify_project", sid, rid, {"project_name_keyword": keyword})

    # 保险类特殊处理：关键词命中直接返回，不调 API
    if any(k in keyword for k in _INSURANCE_KEYWORDS):
        result: dict = {
            "project_name_keyword": keyword,
            "projects": [{"project_id": "9999", "project_name": "保险项目"}],
        }
        result_json: str = json.dumps(result, ensure_ascii=False)
        log_tool_end("classify_project", sid, rid, {"matched": ["保险项目"]})
        return result_json

    # 调用 DataManager API
    try:
        if not DATA_MANAGER_URL:
            return "Error: DATA_MANAGER_URL 未配置"

        url: str = f"{DATA_MANAGER_URL}{SEARCH_PACKAGE_PATH}"
        payload: dict[str, str | int] = {
            "keyword": keyword,
            "top_k": 5,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            resp_data: dict = response.json()

        if resp_data.get("status") != 0:
            return f"Error: {resp_data.get('message', '未知错误')}"

        result_obj: dict = resp_data.get("result") or {}

        def _parse_items(items: list[dict]) -> list[dict[str, str | bool]]:
            """将 API 返回的 package 列表转为精简格式。"""
            parsed: list[dict[str, str | bool]] = []
            for item in items:
                parsed.append({
                    "id": str(item.get("packageId", "")),
                    "name": item.get("packageName", ""),
                    "path": item.get("path") or "",
                    "leaf": bool(item.get("last", False)),
                })
            return parsed

        exact: list[dict[str, str | bool]] = _parse_items(
            result_obj.get("exactMatched") or [],
        )
        fuzzy: list[dict[str, str | bool]] = _parse_items(
            result_obj.get("fuzzyMatched") or [],
        )

        # ragMatched 结构: [{originalName, candidates: [...]}]
        rag_raw: list[dict] = result_obj.get("ragMatched") or []
        rag: list[dict[str, str | bool]] = []
        for group in rag_raw:
            rag.extend(_parse_items(group.get("candidates") or []))

        data: dict = {
            "keyword": keyword,
            "exact": exact,
            "fuzzy": fuzzy,
            "rag": rag,
        }
        result_json = json.dumps(data, ensure_ascii=False)

        all_names: list[str] = [
            p["name"] for p in exact + fuzzy + rag if isinstance(p.get("name"), str)
        ]
        log_tool_end("classify_project", sid, rid, {
            "exact": len(exact), "fuzzy": len(fuzzy), "rag": len(rag),
            "matched": all_names,
        })
        return result_json

    except Exception as e:
        log_tool_end("classify_project", sid, rid, exc=e)
        return f"Error: classify_project failed - {e}"


classify_project.__doc__ = _DESCRIPTION

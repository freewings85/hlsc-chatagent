"""classify_project 工具：粗粒度项目分类，将用户描述归到项目大类。

调用 DataManager 的 searchPackageByKeyword 接口，将关键词匹配到项目大类。
保险类关键词特殊处理，直接返回保险项目，不调 API。

内部决策逻辑：
1. exact 有值 → 直接返回
2. exact 为空 → 看 rag，按 score 阈值过滤
   - 超过阈值的取 top MAX_RESULTS 个
   - 都低于阈值：≤ MAX_RESULTS 个全返回，> MAX_RESULTS 个标记需确认
3. 返回结果带 notice 字段指导 LLM 行为
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

# ---- 配置 ----
RAG_SCORE_THRESHOLD: float = float(os.getenv("CLASSIFY_RAG_THRESHOLD", "0.5"))
MAX_RESULTS: int = int(os.getenv("CLASSIFY_MAX_RESULTS", "3"))


def _parse_item(item: dict) -> dict[str, str | bool | float]:
    """将 API 返回的 package 转为精简格式。"""
    return {
        "id": str(item.get("packageId", "")),
        "name": item.get("packageName", ""),
        "path": item.get("path") or "",
        "leaf": bool(item.get("last", False)),
        "score": float(item.get("similarity", 0)),
    }


def _select_projects(
    exact: list[dict],
    rag_raw: list[dict],
) -> tuple[list[dict[str, str | bool | float]], str]:
    """根据匹配结果决策返回哪些项目 + notice。

    Returns:
        (projects, notice)
    """
    # 1. exact 有值 → 直接返回
    if exact:
        projects: list[dict[str, str | bool | float]] = [_parse_item(it) for it in exact]
        projects = projects[:MAX_RESULTS]
        names: str = "、".join(p["name"] for p in projects)
        notice: str = f"精确匹配到了相关项目：{names}"
        return projects, notice

    # 2. 看 rag（按 score 降序）
    all_candidates: list[dict] = []
    for group in rag_raw:
        for candidate in group.get("candidates") or []:
            all_candidates.append(candidate)

    if not all_candidates:
        return [], "未找到匹配项目"

    # 按 score 降序
    all_candidates.sort(key=lambda x: float(x.get("similarity", 0)), reverse=True)

    # 超过阈值的
    above: list[dict] = [c for c in all_candidates if float(c.get("similarity", 0)) >= RAG_SCORE_THRESHOLD]

    if above:
        # 有超过阈值的 → 取 top MAX_RESULTS
        projects = [_parse_item(it) for it in above[:MAX_RESULTS]]
        names: str = "、".join(p["name"] for p in projects)
        if len(projects) == 1:
            notice = f"匹配到了可能相关的项目：{names}"
        else:
            notice = f"匹配到了多个可能相关的项目：{names}"
        return projects, notice

    # 都低于阈值
    if len(all_candidates) <= MAX_RESULTS:
        # 数量不多 → 全返回
        projects = [_parse_item(it) for it in all_candidates]
        names = "、".join(p["name"] for p in projects)
        notice = f"匹配到了多个可能相关的项目：{names}"
        return projects, notice
    else:
        # 太多且都不确定 → 返回 top MAX_RESULTS + 提示确认
        projects = [_parse_item(it) for it in all_candidates[:MAX_RESULTS]]
        names = "、".join(p["name"] for p in projects)
        notice = f"匹配到了多个可能相关的项目：{names}，建议让用户确认方向"
        return projects, notice


async def classify_project(
    ctx: RunContext[AgentDeps],
    project_name_keyword: Annotated[str, Field(description="用户提到的养车项目名称关键词，只传项目名，不含价格、偏好等修饰语。如'换机油'、'轮胎'、'保养'")],
) -> str:
    """粗粒度项目分类，将用户描述归到项目大类。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    keyword: str = project_name_keyword.strip()
    log_tool_start("classify_project", sid, rid, {"project_name_keyword": keyword})

    if not keyword:
        return json.dumps({"keyword": "", "projects": [], "notice": "未提供项目关键词"}, ensure_ascii=False)

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
        exact_raw: list[dict] = result_obj.get("exactMatched") or []
        rag_raw: list[dict] = result_obj.get("ragMatched") or []

        # 内部决策：选择返回哪些项目
        projects, notice = _select_projects(exact_raw, rag_raw)

        data: dict = {
            "keyword": keyword,
            "projects": projects,
            "notice": notice,
        }
        result_json = json.dumps(data, ensure_ascii=False)

        log_tool_end("classify_project", sid, rid, {
            "count": len(projects),
            "notice": notice,
            "matched": [p["name"] for p in projects],
        })
        return result_json

    except Exception as e:
        log_tool_end("classify_project", sid, rid, exc=e)
        return f"Error: classify_project failed - {e}"


classify_project.__doc__ = _DESCRIPTION

"""search_coupon 工具：查询商户优惠活动。

调用 datamanager getCommercialActivityListPage 接口，
根据商户 ID、项目 ID、模糊关键词查询优惠活动。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.search_activity_service import (
    ActivityItem,
    ActivityPageResult,
    search_activity_service,
)
from hlsc.tools.prompt_loader import load_tool_prompt

logger: logging.Logger = logging.getLogger(__name__)

_DESCRIPTION: str = load_tool_prompt("search_coupon")


async def search_coupon(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[Optional[list[int]], Field(description="项目 ID 列表，来自 classify_project。无明确项目时传 null")] = None,
    shop_ids: Annotated[Optional[list[int]], Field(description="商户 ID 列表，来自 search_shops, 无明确商户时传 null。")] = None,
    semantic_query: Annotated[list[str], Field(description="用户对优惠的自然语言偏好描述（不应该包含地址描述），提取关键词。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数")] = [],
    top_k: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
) -> str:
    """根据项目、商户和语义条件查询可用的优惠活动。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_coupon", sid, rid, {
        "project_ids": project_ids, "shop_ids": shop_ids,
        "semantic_query": semantic_query, "top_k": top_k,
    })

    try:
        fuzzy_keywords: list[str] = []

        # 1. semantic_query → fuzzy 关键词
        if semantic_query:
            fuzzy_keywords.extend(semantic_query)

        # 2. 通过 fusionSearch 扩展 fuzzy 关键词
        if fuzzy_keywords:
            from hlsc.services.restful.fusion_search_service import (
                fusion_search_service, DOC_COMMERCIAL_ACTIVITY,
            )
            result = await fusion_search_service.search(
                keywords=fuzzy_keywords,
                doc_names=[DOC_COMMERCIAL_ACTIVITY],
                session_id=sid,
                request_id=rid,
            )
            expanded: list[str] = result.get_titles(DOC_COMMERCIAL_ACTIVITY)
            if expanded:
                fuzzy_keywords.extend(expanded)
                fuzzy_keywords = list(set(fuzzy_keywords))
            else:
                fuzzy_keywords = []
        logger.info("[search_coupon] 步骤1-2完成: fuzzy_keywords=%s", fuzzy_keywords)

        # 3. 调用 search_activity_service
        logger.info("[search_coupon] 步骤3 请求参数: shop_ids=%s, project_ids=%s, fuzzy=%s, top_k=%s",
                    shop_ids, project_ids, fuzzy_keywords, top_k)

        page_result: ActivityPageResult = await search_activity_service.search(
            page_size=top_k,
            commercial_ids=shop_ids if shop_ids else None,
            package_ids=project_ids if project_ids else None,
            fuzzy=fuzzy_keywords if fuzzy_keywords else None,
            session_id=sid,
            request_id=rid,
        )
        logger.info("[search_coupon] 步骤3完成: total=%d, 返回 %d 条", page_result.total, len(page_result.items))

        if not page_result.items:
            log_tool_end("search_coupon", sid, rid, {"activity_count": 0})
            return "未找到符合条件的优惠活动"

        # 4. 格式化结果
        activities: list[dict] = [_format_activity(item) for item in page_result.items]

        log_tool_end("search_coupon", sid, rid, {
            "activity_count": len(activities),
            "total": page_result.total,
        })
        return json.dumps({
            "total": page_result.total,
            "activities": activities,
        }, ensure_ascii=False)

    except Exception as e:
        log_tool_end("search_coupon", sid, rid, exc=e)
        return f"Error: search_coupon failed - {e}"


def _format_activity(item: ActivityItem) -> dict:
    """将 ActivityItem 格式化为返回给 LLM 的标准 dict。"""
    return {
        "activity_id": item.activity_id,
        "commercial_id": item.commercial_id,
        "package_name": item.package_name,
        "content": item.content,
        "description": item.description,
        "start_time": item.start_time,
        "end_time": item.end_time,
    }


search_coupon.__doc__ = _DESCRIPTION

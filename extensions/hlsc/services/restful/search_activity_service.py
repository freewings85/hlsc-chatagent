"""商户活动查询服务

调用 datamanager /Activity/getCommercialActivityListPage 接口，
根据商户 ID、项目 ID、模糊关键词等条件分页查询商户活动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class ActivityItem:
    """单条商户活动"""

    activity_id: int = 0
    commercial_id: int = 0
    activity_type: int = 0
    package_id: int = 0
    package_name: str = ""
    audit_status: int = 0
    content: str = ""
    description: str = ""
    purchase_limit: int = 0
    purchased_number: int = 0
    invite_count: int = 0
    need_vin: int = 0
    start_time: str = ""
    end_time: str = ""
    create_time: str = ""
    has_stock: bool = False

    @classmethod
    def from_api(cls, raw: dict) -> ActivityItem:
        """从接口返回的 dict 构建。"""
        return cls(
            activity_id=raw.get("activityId", 0),
            commercial_id=raw.get("commercialId", 0),
            activity_type=raw.get("activityType", 0),
            package_id=raw.get("packageId", 0),
            package_name=raw.get("packageName") or "",
            audit_status=raw.get("auditStatus", 0),
            content=raw.get("content") or "",
            description=raw.get("description") or "",
            purchase_limit=raw.get("purchaseLimit", 0),
            purchased_number=raw.get("purchasedNumber", 0),
            invite_count=raw.get("inviteCount", 0),
            need_vin=raw.get("needVin", 0),
            start_time=str(raw.get("startTime") or ""),
            end_time=str(raw.get("endTime") or ""),
            create_time=str(raw.get("createTime") or ""),
            has_stock=bool(raw.get("hasStock", False)),
        )


@dataclass
class ActivityPageResult:
    """分页查询结果"""

    total: int = 0
    page_index: int = 1
    page_size: int = 10
    items: list[ActivityItem] = field(default_factory=list)


# ============================================================
# 服务实现
# ============================================================


class SearchActivityService:
    """商户活动查询服务"""

    async def search(
        self,
        page_index: int = 1,
        page_size: int = 20,
        commercial_ids: list[int] | None = None,
        package_ids: list[int] | None = None,
        fuzzy: list[str] | None = None,
        session_id: str = "",
        request_id: str = "",
    ) -> ActivityPageResult:
        """分页查询商户活动。

        Args:
            page_index: 页码，从 1 开始
            page_size: 每页数量
            commercial_ids: 商户 ID 列表（可选）
            package_ids: 项目包 ID 列表（可选）
            fuzzy: 模糊搜索关键词列表（可选）
            session_id: 会话 ID，透传给后端
            request_id: 请求 ID

        Raises:
            RuntimeError: DATA_MANAGER_URL 未配置或 API 返回错误状态
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/Activity/getCommercialActivityListPage"
        payload: dict = {
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if commercial_ids is not None:
            payload["commercialIds"] = commercial_ids
        if package_ids is not None:
            payload["packageIds"] = package_ids
        if fuzzy is not None:
            payload["fuzzy"] = fuzzy
        if session_id:
            payload["sessionId"] = session_id

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"查询商户活动失败: {data.get('message', '未知错误')}")

        raw_result: dict = data.get("result", {})
        items: list[ActivityItem] = [
            ActivityItem.from_api(item) for item in raw_result.get("list", [])
        ]

        return ActivityPageResult(
            total=raw_result.get("total", 0),
            page_index=raw_result.get("pageIndex", page_index),
            page_size=raw_result.get("pageSize", page_size),
            items=items,
        )


search_activity_service: SearchActivityService = SearchActivityService()

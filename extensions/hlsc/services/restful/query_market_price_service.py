"""项目行情价查询服务 — 查询项目的市场行情参考价（不依赖门店和位置）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_MARKET_PRICE_PATH: str = "/service_ai_datamanager/quotation/quotationIndustryByPackageId"


@dataclass
class MarketPartPrice:
    """配件行情价"""
    part_name: str
    epc_part_name: str
    price: float


@dataclass
class MarketPlan:
    """行情方案"""
    name: str
    type: str
    price: str
    qa: Optional[str] = None
    part_prices: List[MarketPartPrice] = field(default_factory=list)


@dataclass
class MarketProject:
    """项目行情价"""
    project_id: int
    project_name: str
    plans: List[MarketPlan] = field(default_factory=list)


@dataclass
class MarketPriceResult:
    """行情价查询结果"""
    projects: List[MarketProject] = field(default_factory=list)


class QueryMarketPriceService:
    """项目行情价查询服务"""

    async def query(
        self,
        project_ids: List[int],
        car_model_id: str,
        session_id: str = "",
        request_id: str = "",
    ) -> MarketPriceResult:
        """查询项目行情价。

        Args:
            project_ids: 项目 ID 列表
            car_model_id: 车型编码（L2 精度）
            session_id: 会话 ID
            request_id: 请求 ID

        Raises:
            RuntimeError: URL 未配置或 API 返回错误
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")
        url: str = f"{DATA_MANAGER_URL}{_MARKET_PRICE_PATH}"

        if not project_ids:
            return MarketPriceResult()

        payload: dict = {
            "carKey": car_model_id,
            "projectPackageIds": list(set(project_ids)),
        }

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return _parse_result(data.get("result", {}))
            else:
                error_msg: str = data.get("message", "未知错误")
                raise RuntimeError(f"查询行情价失败: {error_msg}")


def _parse_result(raw: dict) -> MarketPriceResult:
    """解析行情价 API 响应。"""
    projects: List[MarketProject] = []
    for p in (raw.get("quotationProjectList") or []):
        plans: List[MarketPlan] = []
        for plan in (p.get("quotationPlanList") or []):
            part_prices: List[MarketPartPrice] = []
            for pp in (plan.get("partPrices") or []):
                for item in (pp.get("partItems") or []):
                    # 过滤无效配件（wareId=0 表示无适配商品）
                    if item.get("wareId", 0) == 0:
                        continue
                    part_prices.append(MarketPartPrice(
                        part_name=pp.get("primaryPartName", ""),
                        epc_part_name=pp.get("epcPartName", ""),
                        price=float(item.get("price", 0)),
                    ))
            plans.append(MarketPlan(
                name=plan.get("name", ""),
                type=plan.get("type", ""),
                price=str(plan.get("price", "")),
                qa=plan.get("qa") or None,
                part_prices=part_prices,
            ))
        projects.append(MarketProject(
            project_id=p.get("id", 0),
            project_name=p.get("name", ""),
            plans=plans,
        ))
    return MarketPriceResult(projects=projects)


query_market_price_service: QueryMarketPriceService = QueryMarketPriceService()

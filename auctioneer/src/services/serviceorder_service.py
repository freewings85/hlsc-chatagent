"""服务订单服务 — 封装 serviceorder 相关 API 调用。

支持四个接口：
- detail: 获取订单详情（状态 + 报价列表）
- discuss/command: 询价途中发出指令（广播 / 要求重新报价）
- commit: 确认选择某商户报价
- cancel: 取消订单（竞价到期无人报价时）
"""

from __future__ import annotations

import os

import httpx

from agent_sdk.logging import log_http_request, log_http_response

SERVICEORDER_URL: str = os.getenv("SERVICEORDER_URL", "")
DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


class ServiceOrderService:
    """服务订单 API 封装"""

    async def get_order_detail(
        self,
        order_id: str,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """获取订单详情：状态 + 商户报价列表。"""
        url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/task/result"
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        payload: dict[str, str] = {"taskId": order_id}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"获取订单详情失败: {data.get('message', '未知错误')}"
            )

    async def discuss_command(
        self,
        order_id: str,
        command: str,
        content: str,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """询价途中发出指令：仅广播或要求商户重新报价。"""
        url: str = f"{SERVICEORDER_URL}/serviceorder/discuss/command"
        if not SERVICEORDER_URL:
            raise RuntimeError("SERVICEORDER_URL 未配置")

        payload: dict[str, str] = {
            "orderId": order_id,
            "command": command,
            "content": content,
        }
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"发出讨论指令失败: {data.get('message', '未知错误')}"
            )

    async def commit_order(
        self,
        order_id: str,
        commercial_id: int,
        operator_name: str = "AI",
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """确认选择某商户的报价，提交订单。"""
        url: str = f"{SERVICEORDER_URL}/serviceorder/commit"
        if not SERVICEORDER_URL:
            raise RuntimeError("SERVICEORDER_URL 未配置")

        payload: dict[str, object] = {
            "orderId": order_id,
            "commercialId": commercial_id,
            "operatorName": operator_name,
        }
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"提交订单失败: {data.get('message', '未知错误')}"
            )

    async def cancel_order(
        self,
        order_id: str,
        operator_name: str = "AI",
    ) -> dict:
        """取消订单（竞价到期无人报价时调用）。"""
        url: str = f"{SERVICEORDER_URL}/serviceorder/cancel"
        if not SERVICEORDER_URL:
            raise RuntimeError("SERVICEORDER_URL 未配置")

        payload: dict[str, str] = {
            "orderId": order_id,
            "operatorName": operator_name,
        }
        log_http_request(url, "POST", "", "", payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, "", "", data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"取消订单失败: {data.get('message', '未知错误')}"
            )


serviceorder_service: ServiceOrderService = ServiceOrderService()

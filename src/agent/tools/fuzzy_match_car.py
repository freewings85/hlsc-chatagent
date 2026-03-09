"""fuzzy_match_car_info 工具：模糊匹配车型信息。

根据用户描述的车型关键词，从车型库中匹配最接近的车型信息（car_model_id + car_model_name）。
通过环境变量 CAR_MODEL_MATCH_URL 获取 API 地址。
"""

import json
import os

import httpx
from pydantic_ai import RunContext

from src.agent.deps import AgentDeps


async def fuzzy_match_car_info(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """根据车型关键词模糊匹配车型编码（car_model_id）和名称。

    当用户用自然语言描述车型（如"奔驰C级"、"宝马3系"）时，
    用此工具获取精确的 car_model_id，供竞价等工具使用。

    Args:
        query: 车型关键词，如"宝马X3"、"奔驰C级 2023款"、"凯美瑞"。

    Returns:
        匹配到的车型信息 JSON（含 car_model_id, car_model_name），
        或未匹配到的提示文字。
    """
    # 优先从 skill_env 读取（config.env 注入），再从进程 env 读取
    url = (
        ctx.deps.skill_env.get("CAR_MODEL_MATCH_URL")
        or os.getenv("CAR_MODEL_MATCH_URL", "")
    )
    if not url:
        return json.dumps({"error": "CAR_MODEL_MATCH_URL 未配置"})

    payload = {
        "queryKey": query,
        "conversationId": ctx.deps.session_id,
    }

    # 绕过代理
    no_proxy = ctx.deps.skill_env.get("no_proxy", os.getenv("no_proxy", ""))

    try:
        transport = httpx.AsyncHTTPTransport(proxy=None) if no_proxy else None
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == 0:
                result = data.get("result")
                if result and result.get("car_key"):
                    return json.dumps({
                        "car_model_id": result["car_key"],
                        "car_model_name": result.get("car_name", ""),
                        "notice": "这是根据关键词匹配的车型。请在回复中告知用户按哪个车型报价，并提示车型不对可以修改。",
                    }, ensure_ascii=False)

            return json.dumps({"error": f"未找到匹配'{query}'的车型"})

    except Exception as e:
        return json.dumps({"error": f"车型匹配失败: {e}"})

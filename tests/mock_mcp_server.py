"""Mock MCP Server：提供天气查询工具，用于测试 MCP 集成。

启动方式：uv run python tests/mock_mcp_server.py
默认地址：http://localhost:8199/mcp
"""

from __future__ import annotations

import random

from fastmcp import FastMCP

mcp = FastMCP("weather-service", instructions="天气查询服务，提供城市天气信息。")


@mcp.tool()
def get_weather(city: str) -> str:
    """获取指定城市的当前天气信息。

    Args:
        city: 城市名称，如"北京"、"上海"
    """
    # 模拟天气数据
    conditions = ["晴", "多云", "阴", "小雨", "大雨", "雪"]
    temp = random.randint(-5, 38)
    humidity = random.randint(20, 95)
    condition = random.choice(conditions)

    return f"{city}当前天气：{condition}，温度 {temp}°C，湿度 {humidity}%"


@mcp.tool()
def get_forecast(city: str, days: int = 3) -> str:
    """获取指定城市未来几天的天气预报。

    Args:
        city: 城市名称
        days: 预报天数（1-7），默认3天
    """
    if days < 1 or days > 7:
        return "预报天数必须在 1-7 之间"

    conditions = ["晴", "多云", "阴", "小雨", "大雨"]
    lines = [f"{city}未来 {days} 天天气预报："]
    for i in range(1, days + 1):
        temp_high = random.randint(15, 35)
        temp_low = temp_high - random.randint(5, 15)
        condition = random.choice(conditions)
        lines.append(f"  第{i}天：{condition}，{temp_low}~{temp_high}°C")

    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn

    # 使用 Streamable HTTP transport
    app = mcp.http_app(path="/mcp")
    uvicorn.run(app, host="0.0.0.0", port=8199)

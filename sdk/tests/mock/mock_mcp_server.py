"""Mock MCP Server：模拟 cjml-cheap-weixiu 的修理厂搜索工具。

启动方式：
    uv run python tests/mock/mock_mcp_server.py [--port 8200]

接入方式：
    在 chatagent 前端 Settings > MCP 中添加：
    URL: http://127.0.0.1:8200/mcp
"""

from __future__ import annotations

import argparse
import json
import random

from fastmcp import FastMCP

mcp = FastMCP("cheap-weixiu-mock", instructions="车辆维修服务工具集（mock）")

# --------------------------------------------------------------------------- #
# Mock 数据
# --------------------------------------------------------------------------- #

_MOCK_SHOPS = [
    {
        "shop_id": "S10001",
        "name": "途虎养车（朝阳大悦城店）",
        "address": "北京市朝阳区朝阳北路101号",
        "distance": "1.2km",
        "rating": 4.8,
        "review_count": 326,
        "phone": "010-88001001",
        "tags": ["保养", "轮胎", "快修快保"],
    },
    {
        "shop_id": "S10002",
        "name": "驰加汽车服务（望京店）",
        "address": "北京市朝阳区望京西路50号",
        "distance": "2.5km",
        "rating": 4.6,
        "review_count": 218,
        "phone": "010-88002002",
        "tags": ["轮胎", "底盘", "四轮定位"],
    },
    {
        "shop_id": "S10003",
        "name": "华胜奔驰宝马奥迪专修（三元桥店）",
        "address": "北京市朝阳区霄云路26号",
        "distance": "3.8km",
        "rating": 4.9,
        "review_count": 512,
        "phone": "010-88003003",
        "tags": ["奔驰专修", "宝马专修", "奥迪专修", "变速箱"],
    },
    {
        "shop_id": "S10004",
        "name": "小拇指汽修（大望路店）",
        "address": "北京市朝阳区大望路SOHO现代城",
        "distance": "4.1km",
        "rating": 4.5,
        "review_count": 189,
        "phone": "010-88004004",
        "tags": ["钣喷", "快修", "保养"],
    },
    {
        "shop_id": "S10005",
        "name": "中鑫之宝（国贸店）",
        "address": "北京市朝阳区建国门外大街1号",
        "distance": "5.6km",
        "rating": 4.7,
        "review_count": 403,
        "phone": "010-88005005",
        "tags": ["豪华车专修", "保养", "发动机", "变速箱"],
    },
]


# --------------------------------------------------------------------------- #
# 工具定义 — 描述直接拷贝自 cjml-cheap-weixiu
# --------------------------------------------------------------------------- #


@mcp.tool(
    description=(
        "搜索用户附近的服务门店。\n\n"
        "前端会自动渲染门店列表，你不需要复述详情。\n\n"
        "Usage:\n"
        "- 用户想找服务门店\n"
        "- 诊断后用户询问去哪里修\n"
        "- 用户问\"附近有修理厂吗\"、\"附近有门店吗\"\n"
        "- 用户问\"哪里可以换/修某个部件\"（核心意图是找门店，不是诊断）\n\n"
        "Usage notes:\n"
        "- 使用上下文地址定位附近门店，如需切换地址请先调用 change_context_location"
    ),
)
def search_repair_shops(keyword: str | None = None) -> str:
    """搜索附近的修理厂。

    Args:
        keyword: 按维修项目筛选，如'刹车'、'保养'、'奔驰专修'
    """
    # 根据 keyword 过滤
    if keyword:
        kw = keyword.lower()
        matched = [
            s for s in _MOCK_SHOPS
            if kw in s["name"].lower()
            or any(kw in t.lower() for t in s["tags"])
        ]
    else:
        matched = _MOCK_SHOPS

    # 模拟随机选取 2~N 家（让结果有点变化）
    if len(matched) > 2:
        matched = random.sample(matched, k=random.randint(2, len(matched)))

    total = len(matched)

    # 按卡片协议输出 card 块
    card_data = json.dumps({
        "total": total,
        "items": matched,
    }, ensure_ascii=False)

    lines: list[str] = []

    # card 块 — loop 会识别并发 SSE 事件给前端
    lines.append(f"<!--card:search_repair_shops-->")
    lines.append(card_data)
    lines.append("<!--/card-->")

    # description — 给 LLM 看的摘要
    if total == 0:
        lines.append("附近没有找到合适的修理厂")
    else:
        lines.append(f"找到 {total} 家修理厂：")
        lines.append("")
        for i, item in enumerate(matched, 1):
            tags_text = f"  标签: {', '.join(item['tags'])}" if item.get("tags") else ""
            lines.append(
                f"{i}. {item['name']}(shopId={item['shop_id']}) — {item['distance']} — 评分{item['rating']}"
            )
            if item.get("address"):
                lines.append(f"   地址: {item['address']}")
            if tags_text:
                lines.append(f"  {tags_text}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 启动入口
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock MCP Server for cheap-weixiu tools")
    parser.add_argument("--port", type=int, default=8200, help="服务端口（默认 8200）")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址")
    args = parser.parse_args()

    print(f"Mock MCP Server starting on http://{args.host}:{args.port}/mcp")
    mcp.run(transport="streamable-http", host=args.host, port=args.port)

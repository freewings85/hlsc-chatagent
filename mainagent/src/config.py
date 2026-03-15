"""MainAgent 业务配置（从环境变量读取）"""

from __future__ import annotations

import os

DEMO_PRICE_FINDER_URL: str = os.getenv("DEMO_PRICE_FINDER_URL", "http://localhost:8101")
"""DemoPriceFinder Subagent 的 A2A 地址"""

CONFIRM_PROJECT_URL: str = os.getenv("CONFIRM_PROJECT_URL", "http://localhost:8102")
"""ConfirmProject Subagent 的 A2A 地址"""

RECOMMEND_PROJECT_URL: str = os.getenv("RECOMMEND_PROJECT_URL", "http://localhost:8103")
"""RecommendProject Subagent 的 A2A 地址"""

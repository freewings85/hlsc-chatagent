"""MainAgent 业务配置（从环境变量读取）"""

from __future__ import annotations

import os

DEMO_PRICE_FINDER_URL: str = os.getenv("DEMO_PRICE_FINDER_URL", "http://localhost:8101")
"""DemoPriceFinder Subagent 的 A2A 地址"""

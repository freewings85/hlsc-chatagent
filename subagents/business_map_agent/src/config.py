"""BusinessMapAgent 配置：从环境变量读取业务地图目录路径。"""

from __future__ import annotations

import os
from pathlib import Path


def get_business_map_dir() -> Path:
    """获取业务地图 YAML 目录路径。

    优先读取 ``BUSINESS_MAP_DIR`` 环境变量；
    未设置时回退到相对路径 ``../../mainagent/business-map``。
    """
    env_val: str = os.getenv("BUSINESS_MAP_DIR", "")
    if env_val:
        return Path(env_val)
    # 默认：subagents/business_map_agent/ 相对于 mainagent/business-map/
    return Path(__file__).resolve().parent.parent.parent.parent / "mainagent" / "business-map"

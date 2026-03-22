"""RecommendProject 工具集。"""

from typing import Any

from src.tools.recommend_projects_api import recommend_projects_api
from hlsc.tools.fuzzy_match_car_info import fuzzy_match_car_info


def create_recommend_project_tool_map() -> dict[str, Any]:
    return {
        "recommend-projects": recommend_projects_api,
        "fuzzy_match_car_info": fuzzy_match_car_info,
    }


__all__ = [
    "recommend_projects_api",
    "create_recommend_project_tool_map",
]

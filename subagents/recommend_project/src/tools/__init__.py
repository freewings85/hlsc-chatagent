"""RecommendProject 工具集。"""

from typing import Any

from src.tools.recommend_projects_api import recommend_projects_api
from src.tools.search_project_by_keyword import search_project_by_keyword
from hlsc.tools.fuzzy_match_car_info import fuzzy_match_car_info


def create_recommend_project_tool_map() -> dict[str, Any]:
    return {
        "recommend-projects": recommend_projects_api,
        "search-project-by-keyword": search_project_by_keyword,
        "fuzzy_match_car_info": fuzzy_match_car_info,
    }


__all__ = [
    "recommend_projects_api",
    "search_project_by_keyword",
    "create_recommend_project_tool_map",
]

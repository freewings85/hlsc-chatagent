"""RecommendProject 工具集。"""

from typing import Any

from src.tools.recommend_projects import recommend_projects
from src.tools.ask_user_select_project import ask_user_select_project
from hlsc.tools.fuzzy_match_car_info import fuzzy_match_car_info


def create_recommend_project_tool_map() -> dict[str, Any]:
    return {
        "recommend_projects": recommend_projects,
        "ask_user_select_project": ask_user_select_project,
        "fuzzy_match_car_info": fuzzy_match_car_info,
    }


__all__ = [
    "recommend_projects",
    "ask_user_select_project",
    "create_recommend_project_tool_map",
]

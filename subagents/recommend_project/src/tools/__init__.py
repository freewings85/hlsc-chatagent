"""RecommendProject 工具集。"""

from typing import Any

from src.tools.recommend_projects import recommend_projects
from src.tools.ask_user_select_project import ask_user_select_project
from hlsc.tools.get_representative_car_model import get_representative_car_model


def create_recommend_project_tool_map() -> dict[str, Any]:
    return {
        "recommend_projects": recommend_projects,
        "ask_user_select_project": ask_user_select_project,
        "get_representative_car_model": get_representative_car_model,
    }


__all__ = [
    "recommend_projects",
    "ask_user_select_project",
    "create_recommend_project_tool_map",
]

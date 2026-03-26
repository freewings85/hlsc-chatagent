"""项目相关 mock 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

try:
    from .mock_data import (
        CAR_MODEL,
        FAULTS,
        PENDING_PROJECTS_BY_USER,
        PRIMARY_PARTS,
        PRIMARY_PART_TO_PROJECT_IDS,
        PROJECT_DETAILS,
        PROJECT_HISTORY_BY_USER,
        PROJECTS,
        PROJECT_TREE,
        RELATED_PROJECT_IDS,
        TRIGGER_CONDITIONS,
        get_project,
        public_project,
    )
except ImportError:
    from routes.mock_data import (
        CAR_MODEL,
        FAULTS,
        PENDING_PROJECTS_BY_USER,
        PRIMARY_PARTS,
        PRIMARY_PART_TO_PROJECT_IDS,
        PROJECT_DETAILS,
        PROJECT_HISTORY_BY_USER,
        PROJECTS,
        PROJECT_TREE,
        RELATED_PROJECT_IDS,
        TRIGGER_CONDITIONS,
        get_project,
        public_project,
    )

router: APIRouter = APIRouter(tags=["projects"])


def _ok(result: Any) -> dict[str, Any]:
    return result


def _match_score(text: str, project: dict[str, Any]) -> float:
    haystacks = [project["project_name"], project["project_simple_name"], *project["keywords"]]
    text_l = text.lower()
    best = 0.0
    for value in haystacks:
        value_l = value.lower()
        if text_l == value_l:
            best = max(best, 0.99)
            continue
        if text_l in value_l or value_l in text_l:
            best = max(best, 0.96)
            continue
        overlap = sum(1 for token in project["keywords"] if token.lower() in text_l)
        if overlap:
            best = max(best, 0.8 + overlap * 0.05)
    if best > 0:
        return min(best, 0.98)
    return 0.65


@router.post("/service_ai_datamanager/project/searchProjectPackageByKeyword")
async def search_project_by_keyword(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    search_text = str(payload.get("search_text") or "")
    top_k = int(payload.get("top_k", 5))
    matched = []
    for project in PROJECTS:
        score = _match_score(search_text, project)
        if score >= float(payload.get("similarity_threshold", 0)):
            matched.append({"project": public_project(project), "match_data": {"similarity": score}})
    matched.sort(key=lambda item: item["match_data"]["similarity"], reverse=True)
    return _ok({"query": {"search_text": search_text}, "items": matched[:top_k]})


@router.post("/service_ai_datamanager/partprimary/searchPartPrimaryByKeyword")
async def search_primary_part(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    search_text = str(payload.get("search_text") or "").lower()
    top_k = int(payload.get("top_k", 5))
    items = [
        part for part in PRIMARY_PARTS
        if search_text in part["primary_part_name"].lower()
    ]
    return _ok({"query": {"search_text": search_text}, "items": items[:top_k]})


@router.post("/service_ai_datamanager/projecttriggerconditions/searchprojecttriggerconditions")
async def search_trigger_conditions(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    search_text = str(payload.get("search_text") or "").lower()
    items = [item for item in TRIGGER_CONDITIONS if search_text in item["title"].lower() or search_text in item["content"].lower()]
    return _ok({"query": {"search_text": search_text}, "items": items})


@router.post("/service_ai_datamanager/faultphenomenon/searchfaultphenomenon")
async def search_faultphenomenon(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    search_text = str(payload.get("search_text") or "").lower()
    items = [item for item in FAULTS if search_text in item["title"].lower() or search_text in item["content"].lower()]
    return _ok({"query": {"search_text": search_text}, "items": items})


@router.get("/service_ai_datamanager/Category/allProjectCategoryTree")
async def all_project_category_tree() -> dict[str, Any]:
    return _ok({"items": PROJECT_TREE})


@router.post("/service_ai_datamanager/project/maintainProjectTreeByCarKey")
async def maintain_project_tree(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    project_ids = set(payload.get("project_ids") or [])
    if not project_ids:
        return _ok({"items": PROJECT_TREE})
    filtered_tree = []
    for category in PROJECT_TREE:
        children = [child for child in category["children"] if child["id"] in project_ids]
        if children:
            filtered_tree.append({**category, "children": children})
    return _ok({"items": filtered_tree})


@router.post("/service_ai_datamanager/project/getSampleVinProjects")
async def get_sample_vin_projects(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    items = [{"project_id": project["project_id"], "project_name": project["project_name"]} for project in PROJECTS[:3]]
    return _ok({"vehicle_info": CAR_MODEL, "items": items})


@router.post("/web_owner/project/getProjectDetails")
async def get_project_details(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    project_ids = payload.get("project_ids") or []
    items = []
    for project_id in project_ids:
        project = get_project(int(project_id))
        if project is None:
            continue
        detail = PROJECT_DETAILS.get(project["project_id"], {})
        related_projects = [
            {
                "project_id": related_id,
                "project_name": get_project(related_id)["project_name"],
            }
            for related_id in RELATED_PROJECT_IDS.get(project["project_id"], [])
            if get_project(related_id) is not None
        ]
        items.append(
            {
                "project": public_project(project),
                "detail_data": {
                    **detail,
                    "related_projects": related_projects,
                },
            }
        )
    return _ok({"items": items})


@router.post("/service_ai_datamanager/project/getProjectPackageByPrimaryNameId")
async def get_project_by_primary_part(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    primary_part_ids = payload.get("primary_part_ids") or []
    items = []
    for primary_part_id in primary_part_ids:
        for project_id in PRIMARY_PART_TO_PROJECT_IDS.get(int(primary_part_id), []):
            project = get_project(project_id)
            if project is not None:
                items.append({"project_id": project_id, "project_name": project["project_name"]})
    return _ok({"items": items})


@router.post("/service_ai_datamanager/project/getProjectPackageByProjectId")
async def get_project_by_source_project(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    source_project_ids = payload.get("source_project_ids") or []
    items = []
    for source_project_id in source_project_ids:
        project = next((item for item in PROJECTS if item["source_project_id"] == int(source_project_id)), None)
        if project is not None:
            items.append(
                {
                    "project_id": project["project_id"],
                    "project_name": project["project_name"],
                    "source_project_id": project["source_project_id"],
                }
            )
    return _ok({"items": items})


@router.post("/service_ai_datamanager/project/getRelatedProjectPackageByPackage")
async def get_related_projects(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    project_ids = payload.get("project_ids") or []
    items = []
    for project_id in project_ids:
        for related_id in RELATED_PROJECT_IDS.get(int(project_id), []):
            project = get_project(related_id)
            if project is not None:
                items.append(
                    {
                        "project_id": project["project_id"],
                        "project_name": project["project_name"],
                        "relation_type": "related",
                    }
                )
    return _ok({"items": items})


@router.post("/service_ai_datamanager/project/getHistoryPackage")
async def get_history_package(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user_id = str(payload.get("user_id", ""))
    items = PROJECT_HISTORY_BY_USER.get(user_id, [])
    return _ok({"query": {"user_id": user_id, "mode": "history"}, "items": items})


@router.post("/service_ai_datamanager/project/getPendingPackage")
async def get_pending_package(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user_id = str(payload.get("user_id", ""))
    items = PENDING_PROJECTS_BY_USER.get(user_id, [])
    return _ok({"query": {"user_id": user_id, "mode": "pending"}, "items": items})

"""准备竞价数据：查询项目参数 schema，构建完整的 task_data。

用法：
    python prepare_bidding.py '<json_args>'

输入 JSON 字段：
    project_ids: list[int]      - 项目 ID 列表（必填）
    car_model_id: str           - 车型编码（必填）
    car_model_name: str         - 车型名称（必填）
    description: str            - 需求描述（必填）
    filters: dict | None        - 筛选条件
    context_params: dict | None - 已知项目参数
    preferred_time: str | None  - 期望时间

输出：JSON 格式的 task_data，包含完整的项目参数 schema 和筛选条件。
"""

import asyncio
import json
import sys
from typing import Any


# 筛选条件定义
FILTER_DEFS: list[dict[str, Any]] = [
    {
        "name": "distance_km",
        "label": "距离范围(公里)",
        "input_type": "range",
        "required": False,
        "default": {"min": 0, "max": 30},
        "value_keys": ["distance_min_km", "distance_max_km"],
    },
    {
        "name": "min_rating",
        "label": "最低评分",
        "input_type": "number",
        "required": False,
        "default": None,
    },
]


def build_filters_schema(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """构造筛选条件 schema。"""
    result: list[dict[str, Any]] = []
    for f_def in FILTER_DEFS:
        item: dict[str, Any] = {
            "name": f_def["name"],
            "label": f_def["label"],
            "input_type": f_def["input_type"],
            "required": f_def["required"],
        }

        if f_def["input_type"] == "range":
            nested = filters.get(f_def["name"])
            if isinstance(nested, dict):
                min_val = nested.get("min")
                max_val = nested.get("max")
            else:
                value_keys = f_def.get("value_keys", [])
                min_val = filters.get(value_keys[0]) if len(value_keys) > 0 else None
                max_val = filters.get(value_keys[1]) if len(value_keys) > 1 else None

            if min_val is not None or max_val is not None:
                item["value"] = {"min": min_val, "max": max_val}
            else:
                item["value"] = f_def.get("default")
        else:
            item["value"] = filters.get(f_def["name"], f_def.get("default"))

        result.append(item)
    return result


async def build_projects_with_params(
    project_ids: list[int],
    context_params: dict[str, Any],
) -> list[dict[str, Any]]:
    """查询项目参数 schema 并填充已知值。"""
    try:
        from src.services.restful.get_project_param_schema_service import (
            get_project_param_schema_service,
        )
        schemas = await get_project_param_schema_service.get_schemas(project_ids)
    except Exception:
        # 服务不可用时退化为基本结构
        schemas = {}

    projects: list[dict[str, Any]] = []
    for pid in project_ids:
        schema = schemas.get(str(pid))
        project_name: str = schema.project_name if schema else f"项目{pid}"
        param_defs = schema.params if schema else []

        params: list[dict[str, Any]] = []
        for p_def in param_defs:
            param = {**p_def.to_dict(), "value": context_params.get(p_def.name)}
            params.append(param)

        projects.append({
            "project_id": pid,
            "project_name": project_name,
            "params": params,
        })
    return projects


async def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少参数，用法: python prepare_bidding.py '<json>'"}))
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}))
        sys.exit(1)

    project_ids: list[int] = args.get("project_ids", [])
    car_model_id: str = args.get("car_model_id", "")
    car_model_name: str = args.get("car_model_name", "")
    description: str = args.get("description", "")
    filters: dict[str, Any] = args.get("filters") or {}
    context_params: dict[str, Any] = args.get("context_params") or {}
    preferred_time: str = args.get("preferred_time", "")

    if not project_ids:
        print(json.dumps({"error": "project_ids 不能为空"}))
        sys.exit(1)
    if not car_model_id:
        print(json.dumps({"error": "car_model_id 不能为空"}))
        sys.exit(1)

    # 确保 context_params 包含车型信息
    context_params.setdefault("car_model_id", car_model_id)
    context_params.setdefault("car_model_name", car_model_name)

    # 构建数据
    projects_with_params = await build_projects_with_params(project_ids, context_params)
    filters_schema = build_filters_schema(filters)

    task_data: dict[str, Any] = {
        "status": "pending_confirm",
        "filters": filters_schema,
        "projects": projects_with_params,
        "car_model_id": car_model_id,
        "car_model_name": car_model_name,
        "description": description,
        "preferred_time": preferred_time,
    }

    print(json.dumps(task_data, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

# 项目详情

这份文档解决：
- 已经有 `project_id` 后，补项目详情
- 查保养周期、说明、关联配件、适用商户类型等信息

## 接口

`${API_BASE_URL}/web_owner/project/optimize/getProjectDetails`

## 什么时候用

- 要向上层解释项目是什么
- 要查项目配件、周期、适用商户类型
- 要把项目补成可解释的业务对象

## 入参

必填：
- `project_ids`

可选：
- `car_model_id`

## 返回结果建议

```json
{
  "items": [
    {
      "project": {
        "project_id": 516,
        "project_name": "前刹车片更换",
        "project_simple_name": "前片",
        "description": "",
        "keywords": ["前刹车片", "制动摩擦"],
        "unit": "一对"
      },
      "detail_data": {
        "first_maintenance_mileage": 0,
        "first_maintenance_time_month": 0,
        "maintenance_mileage": 0,
        "maintenance_time_month": 0,
        "related_projects": [],
        "related_parts": [],
        "shop_type_scope": []
      }
    }
  ]
}
```

## 当前任务最重要的返回信息

- `project`
- `detail_data.first_maintenance_mileage`
- `detail_data.first_maintenance_time_month`
- `detail_data.maintenance_mileage`
- `detail_data.maintenance_time_month`
- `detail_data.related_projects`
- `detail_data.related_parts`
- `detail_data.shop_type_scope`

## 使用说明

- 如果任务只需要 `project_id` 和 `project_name`，不要来读这份文档
- 这份文档适合在项目已经确定后，再补全解释能力

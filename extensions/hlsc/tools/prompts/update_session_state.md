更新会话状态。当通过工具调用获得关键信息后，用此工具记录已确认的信息，后续轮次可直接使用，避免重复查询。

## 数据结构

session_state 采用统一的实体列表格式：

```json
{
  "carModels": [{"id": "car_model_id_string", "name": "2021款大众朗逸 1.5L"}],
  "addresses": [{"latitude": 31.23, "longitude": 121.47, "name": "浦东新区"}],
  "projects": [{"id": 1242, "name": "机油/机滤更换"}],
  "shops": [{"id": 109, "name": "嘉定汽修"}],
  "coupons": [{"id": 42, "name": "春季保养促销"}]
}
```

注意：carModels 的 id 是字符串，其余 id 都是数值。

## 使用时机

- classify_project / match_project 返回后 → 记录 projects
- search_shops 用户选定商户后 → 记录 shops
- collect_car_info / list_user_cars 确认车型后 → 记录 carModels
- collect_location + geocode_location 获取位置后 → 记录 addresses
- search_coupon 用户选定优惠后 → 记录 coupons

参数 updates 是一个字典，key 是字段名（如 "projects"），value 是对应的列表。value 为 null 表示清除该字段。

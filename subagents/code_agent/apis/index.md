# 业务 API 索引

以下是所有可用的业务 API。根据用户需求选择需要的 API，然后读取对应的详情文件获取参数和返回值。

## 工单系统

- GET /api/orders/search — 按条件搜索工单（支持时间范围、状态、客户、门店筛选）→ 详情：`orders/search.md`
- GET /api/orders/{id} — 获取工单详情（含维修项目、零件、金额明细）→ 详情：`orders/get_detail.md`
- GET /api/orders/{id}/timeline — 工单进度时间线（各状态变更记录）→ 详情：`orders/timeline.md`
- GET /api/orders/stats — 工单统计（按时间段汇总数量和金额）→ 详情：`orders/stats.md`

## 库存系统

- GET /api/inventory/parts — 查询零件库存和价格（支持名称/编号/分类筛选）→ 详情：`inventory/parts.md`
- GET /api/inventory/suppliers — 查询供应商列表及评级 → 详情：`inventory/suppliers.md`

## 客户系统

- GET /api/customers/search — 搜索客户（按姓名、手机号、车牌号）→ 详情：`customers/search.md`
- GET /api/customers/{id}/vehicles — 获取客户名下车辆列表 → 详情：`customers/vehicles.md`
- GET /api/customers/{id}/repair_history — 获取客户维修历史记录 → 详情：`customers/repair_history.md`

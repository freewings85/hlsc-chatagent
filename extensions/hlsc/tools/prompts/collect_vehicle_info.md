Description:
查询用户车库，返回车辆列表。工具只负责查询，不做选择、不写状态。

Usage notes:
- 调用后返回 `{total, cars: [{car_id, car_name}, ...]}`
- 根据 total 判断：
  - 0 → 车库为空，引导用户通过 collect_user_car_info 录入车辆
  - 1 → 只有一辆，直接调 update_workflow_state 写入该 car_id
  - 多辆 → 根据用户描述（如"我的奥迪"）从列表中判断选哪辆：
    - 能确定 → 调 update_workflow_state 写入 car_id
    - 无法确定 → 列出候选让用户选择，确认后再写入
- car_id 必须来自工具返回的列表，不可自行构造

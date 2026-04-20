Description:
查询用户车库并确定车辆 car_id。

Usage notes:
- 0 辆车 → 返回 `no_cars`，已自动写入空 car_id。引导用户通过 collect_user_car_info 录入车辆
- 1 辆车 → 返回 `auto_selected` + car_id，已自动写入。直接进入下一步
- 多辆车 → 返回 `need_selection` + 候选列表 `[{car_id, car_name}, ...]`：
  - 根据用户描述（如"我的奥迪"）判断选哪辆
  - 能确定 → 调 update_workflow_state 写入 car_id
  - 无法确定 → 列出候选让用户选择，确认后再写入
- car_id 必须来自候选列表，不可自行构造

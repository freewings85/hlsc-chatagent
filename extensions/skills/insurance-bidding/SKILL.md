---
name: insurance-bidding
description: 保险项目竞标预订，帮助用户选择保险，获取多家保险公司的报价
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：确认竞标信息 → 创建订单 → 返回 order_id 卡片。

## 前置条件（LLM 在调用前需确保）

- car_model_id 已确认,如果没有的话，先调用`collect_car_info`
- project_id 已确认（保险项目）
- shop_ids 已确认（参与竞价的商户列表）,如果没有的话，直接执行脚本自动获取（脚本会根据用户档案自动确定城市，不需要问用户）：
  ```bash
  python {SCRIPTS_DIR}/search_insurance_company.py --project_id {project_id}
  ```

## 执行步骤

1. 收集前置条件（project_id、shop_ids、car_model_id），缺失的通过对应工具获取
2. **条件齐备后，执行脚本完成确认和下单**（脚本内部会发送确认卡片给用户、等待回复、创建订单，不需要额外调用其他工具）：

```bash
python {SCRIPTS_DIR}/confirm_and_create.py --project_id 1461 --shop_ids 87,88 --car_model_id 56
```

> `--remark` 可选，仅在用户主动提供备注时才加，不要自行编造。

> `--booking_time` 可选，用户指定了到店时间才传，否则默认"由商户排期"。

> 脚本会自动发送确认卡片、等待用户回复、创建订单并启动竞价，返回 order card。不要用文字模拟脚本行为。

## 完成标准

- 脚本执行成功返回 order card
- 或车主取消了竞标预订

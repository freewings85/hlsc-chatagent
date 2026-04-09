---
name: insurance-bidding
description: 保险项目竞标预订，帮助用户汇总需求信息，选择最优返增的保险
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：收集竞标信息 → 创建订单 → 返回 order_id 卡片。

## 执行步骤（严格按序执行，每步必须调用工具或脚本，不要用文字代替）

### 步骤 1：收集信息
- 如果上下文中不存在 car_model_id，调用 `collect_car_info` 工具获取车型
- 询问用户对保险的需求（期望返现金额、赠送项目等），**返现金额必须要问出来**，汇总到 `remark`

### 步骤 2：获取 shop_ids
project_id 固定 1461，直接执行脚本获取参与竞价的商户：
```bash
python {SCRIPTS_DIR}/search_insurance_company.py --project_id 1461
```

### 步骤 3：发送确认卡片
将用户需求汇总为 remark，用前置步骤获得的参数执行确认脚本：
```bash
python {SCRIPTS_DIR}/confirm_booking.py --project_id 1461 --shop_ids 87,88 --car_model_id 56 --remark '返现800元'
```

脚本返回用户的原始回复文本，只需判断两种意图：
- **确认**（"确认"、"好的"、"可以"等肯定表达）→ 继续步骤 4
- **其他一切回复**（包括取消、修改、犹豫）→ 告知车主已取消，结束

### 步骤 4：创建订单
使用步骤 3 返回的「已确认参数」原样拼接执行，**不要自行重构参数**：
```bash
python {SCRIPTS_DIR}/create_order.py {步骤3返回的已确认参数}
```
> 脚本会创建订单并启动竞价，返回 order card。不要用文字模拟。

## 完成标准

- 脚本执行成功返回 order card
- 或车主未确认，流程结束

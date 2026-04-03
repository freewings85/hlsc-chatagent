---
name: insurance-bidding
description: 保险项目竞标预订，帮助用户选择保险，获取多家保险公司的报价
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：确认竞标信息 → 创建订单 → 返回 order_id 卡片。

## 执行步骤（严格按序执行，每步必须调用工具或脚本，不要用文字代替）

### 步骤 1：收集 car_model_id
如果上下文中不存在car_model_id，调用 `collect_car_info` 工具获取车型。

### 步骤 2：获取 shop_ids
project_id 固定 1461，直接执行脚本获取参与竞价的商户（脚本自动根据用户档案确定城市，不需要问用户）：
```bash
python {SCRIPTS_DIR}/search_insurance_company.py --project_id 1461
```

### 步骤 3：发送确认卡片
用步骤 1、2 获得的参数执行确认脚本：
```bash
python {SCRIPTS_DIR}/confirm_booking.py --project_id 1461 --shop_ids 87,88 --car_model_id 56
```
> `--remark` 可选，仅在用户主动提供备注时才加。

脚本返回用户的原始回复文本。根据回复判断意图：
- **确认**（"确认"、"好的"、"可以"等肯定表达）→ 继续步骤 4
- **取消**（"取消"、"不用了"等否定表达）→ 告知车主已取消，结束
- **想修改** → 根据要求调整参数，重新执行步骤 3
- **其他** → 引导车主确认或说明想调整什么

### 步骤 4：创建订单
使用步骤 3 返回的「已确认参数」原样拼接执行，**不要自行重构参数**：
```bash
python {SCRIPTS_DIR}/create_order.py {步骤3返回的已确认参数}
```
> 脚本会创建订单并启动竞价，返回 order card。不要用文字模拟。

## 完成标准

- 脚本执行成功返回 order card
- 或车主取消了竞标预订

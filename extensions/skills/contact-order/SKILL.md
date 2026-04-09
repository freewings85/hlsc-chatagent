---
name: contact-order
description: 生成联系单，让商户带着用户需求信息主动联系用户
when_to_use: 用户选定了商户，要联系商户或让商户联系自己时
---

# 生成联系单

用户选好商户后，确认必要信息并生成联系单。

## 执行步骤

### 步骤 1：确认商户

确认用户选定的商户（shop_id 和 shop_name 必须来自 search_shops 返回的真实数据）。

### 步骤 2：确认到店时间

如果对话中用户还没说到店时间 → 问一句"您打算什么时候过去？"
支持自然语言，如"明天下午""周六上午""后天"。

### 步骤 3：总结需求

从对话中总结用户需求，作为 task_describe 参数。一句话，至少包含项目名称，有偏好和要求也写进去。不要编造用户没说过的内容。

### 步骤 4：生成联系单

执行脚本：
```bash
python {SCRIPTS_DIR}/create_contact_order.py --shop_id 商户ID --shop_name "商户名称" --visit_time "到店时间" --task_describe "需求描述"
```

脚本会返回 ContactOrderCard，直接展示给用户。

## 完成标准

- 脚本执行成功返回 ContactOrderCard
- 或用户取消了联系

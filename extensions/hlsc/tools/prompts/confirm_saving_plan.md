当用户确认了省钱方式后，你必须立刻调用此工具。

## 调用时机

两个条件都满足时，必须调用：
1. 项目已确认（通过 classify_project 匹配，或保险类固定 project_id="9999"）
2. 用户明确选择了一种省钱方式（如"用九折""帮我竞价""找有优惠的店"）

不要只口头回应"好的帮你用九折"而不调用此工具。用户确认了就必须调。

## saving_method 取值

- `platform_offer` — 用户说"用九折""用优惠券""用平台优惠" → 选此值
- `insurance_bidding` — 用户说"帮我竞价""让多家报价""走保险竞价" → 选此值
- `merchant_promo` — 用户说"找有优惠的店""看商户活动" → 选此值

## 调用后

系统会自动扩展你的能力，你将获得预订下单的完整工具。

## 不调用的情况

- 用户说"不需要优惠""不用了直接做" → 不调用此工具，改为引导提供车辆信息
- 项目还没确认（没调过 classify_project 且不是保险类）→ 先确认项目
- 用户只是想找新商户对比价格 → 不调用此工具，用 search_shops 搜索即可

## 参数来源

- project_id 和 project_name 来自 classify_project 返回的 project_id 和 project_name
- 保险类项目固定：project_id="9999"，project_name="保险项目"，不需要调 classify_project
- 不可编造，必须基于 classify_project 返回值或保险固定值

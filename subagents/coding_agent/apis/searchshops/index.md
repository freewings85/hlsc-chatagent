# searchshops 场景 API 索引

本场景用于帮用户找到最合适的商户，支持多条件组合查询和跨数据源计算。

## 可用 API

### 一、商户搜索
- 搜索附近商户、按条件筛选（语义查询 + 结构化过滤 + 位置过滤）
- 文档：`/apis/searchshops/shops.md`

### 二、优惠活动
- 查商户的优惠券/活动，用于筛选有优惠的商户或计算优惠后价格
- 文档：`/apis/searchshops/coupons.md`

### 三、商户项目报价
- 查指定商户的项目报价，用于比价
- 文档：`/apis/searchshops/quotations.md`

## 典型任务

1. **"哪家换胎用完优惠后最便宜"**
   - 读 shops.md → 搜附近能做换胎的店
   - 读 quotations.md → 查每家店换胎的报价
   - 读 coupons.md → 查每家店的优惠
   - Python 计算：报价 - 优惠 = 最终价格，排序

2. **"评分高、有优惠的修理厂"**
   - 读 shops.md → 搜商户（按评分过滤）
   - 读 coupons.md → 查哪些有优惠
   - Python 过滤：只保留有优惠的

3. **"A店和B店做保养哪个便宜"**
   - 读 quotations.md → 查两家店的保养报价
   - 读 coupons.md → 查两家店的优惠
   - Python 计算对比

4. **"附近有没有4S店"**
   - 读 shops.md → 搜商户，结果中 shop_type 字段包含商户类型（如"4S店"），可在结果中过滤

# searchshops 场景 API 索引

本场景用于帮用户找到最合适的商户，支持多条件组合查询和跨数据源计算。

## 可用 API

### 一、商户搜索
- 搜索附近商户、按条件筛选
- 文档：`/apis/shops/search.md`

### 二、商户类型
- 理解 4S 店、连锁店、独立修理厂的区别
- 文档：`/apis/shops/types.md`

### 三、项目匹配
- 从用户描述匹配到标准项目 ID
- 文档：`/apis/projects/search.md`

### 四、商户报价
- 查指定商户的项目报价，用于比价
- 文档：`/apis/quotations/nearby_shops.md`

### 五、优惠活动
- 查商户的优惠券/活动，用于计算优惠后价格
- 文档：`/apis/searchshops/coupons.md`

## 典型任务

1. **"哪家换胎用完优惠后最便宜"**
   - 读 shops/search.md → 找附近换胎店
   - 读 quotations/nearby_shops.md → 查每家报价
   - 读 searchshops/coupons.md → 查每家优惠
   - Python 计算：报价 - 优惠 = 最终价格，排序

2. **"评分高、有优惠的修理厂"**
   - 读 shops/search.md → 搜商户（min_rating 过滤）
   - 读 searchshops/coupons.md → 查哪些有优惠
   - Python 过滤：只保留有优惠的

3. **"A店和B店做保养哪个便宜"**
   - 读 quotations/nearby_shops.md → 查两家报价
   - 读 searchshops/coupons.md → 查两家优惠
   - Python 计算对比

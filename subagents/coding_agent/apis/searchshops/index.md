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

### 四、项目匹配
- 将用户描述的模糊项目名匹配到标准项目 ID（需要 projectId 时先调此接口）
- 文档：`/apis/searchshops/projects.md`

### 五、地址解析
- 将地址文本转为经纬度，用于调其他 API 的位置参数
- 文档：`/apis/searchshops/address.md`

## 典型任务

1. **"哪家换胎用完优惠后最便宜"**
   - 读 projects.md → "换胎"匹配到 projectId
   - 读 shops.md → 搜附近商户（传 projectIds 筛选能做换胎的）
   - 读 quotations.md → 查每家店该 projectId 的报价
   - 读 coupons.md → 查每家店的优惠
   - Python 计算：报价 - 优惠 = 最终价格，排序

2. **"评分高、有优惠的修理厂"**
   - 读 shops.md → 搜商户（按评分过滤）
   - 读 coupons.md → 查哪些有优惠
   - Python 过滤：只保留有优惠的

3. **"A店和B店做保养哪个便宜"**
   - 读 projects.md → "保养"匹配到 projectId
   - 读 quotations.md → 查两家店该 projectId 的报价
   - 读 coupons.md → 查两家店的优惠
   - Python 计算对比

4. **"附近有没有4S店"**
   - 读 shops.md → 搜商户，结果中 shop_type 字段包含商户类型（如"4S店"），可在结果中过滤

5. **"淮海中路上哪家洗车便宜"**
   - 读 projects.md → "洗车"匹配到 projectId
   - 读 address.md → 解析"淮海中路" → 拿到 lat/lng
   - 读 shops.md → 用 lat/lng 搜附近商户
   - 读 quotations.md → 查每家该 projectId 的报价
   - Python 比价排序

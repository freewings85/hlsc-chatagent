# Mock 数据设置与本地启动

本文档说明如何在本地启动 mainagent（8100 服务），使用 mock 优惠数据进行测试。

## 方案对比

### 方案 A：Pure Mock（推荐用于快速开发和测试）

**优点**：无需启动额外服务，开发速度最快  
**缺点**：数据来自硬编码 mock

**启动步骤**：

```bash
cd mainagent

# .env.local 中已配置 MOCK_SEARCH_COUPON=true，直接启动
uv run python server.py

# 或指定端口
uv run python server.py --port 8100
```

**验证**：
- 打开浏览器访问 http://localhost:8100 或用客户端发送请求
- search_coupon 工具会自动返回 mock 数据（见下方数据说明）

---

### 方案 B：本地 Mock 服务器（推荐用于集成测试）

**优点**：模拟真实 HTTP 调用，数据灵活可扩展  
**缺点**：需要启动额外的服务进程

**启动步骤**：

```bash
cd mainagent

# 终端 1：启动 mock DataManager 服务
uv run python mock_data_server.py --port 50400

# 终端 2：修改 .env.local，启用 DataManager URL
# 改为：DATA_MANAGER_URL=http://127.0.0.1:50400
# 注释：MOCK_SEARCH_COUPON=true

# 启动 mainagent
uv run python server.py --port 8100
```

**验证**：
- Mock 服务器日志会显示每次调用的请求和返回
- mainagent 调用真实的 HTTP 接口（本地 127.0.0.1:50400）

---

### 方案 C：远程 DataManager（生产环境）

**配置**：
```env
DATA_MANAGER_URL=http://192.168.100.108:50400
MOCK_SEARCH_COUPON=false
MOCK_APPLY_COUPON=false
```

**启动**：
```bash
cd mainagent
uv run python server.py
```

---

## Mock 数据说明

### search_coupon 工具返回的数据

**file**: `mainagent/data/mock_coupons.py`

#### 场景 1：有商户优惠 + 平台优惠（默认）
```
- 平台活动 1 条（话痨 9 折）
- 商户活动 3 条（机油 8 折、轮胎 7.5 折、原厂配件 8.5 折）
```

触发条件：使用默认参数调用（无 semantic_query）

#### 场景 2：仅平台优惠（无商户）
```
- 平台活动 1 条（话痨 9 折）
- 商户活动 0 条
```

触发条件：
- 通过 mock 服务器 + semantic_query 包含 "empty"
- 或通过 Pure Mock 且没有指定项目

#### 场景 3：完全无优惠（空）
```
- 平台活动 0 条
- 商户活动 0 条
```

触发条件：semantic_query 包含 "empty" 或返回错误

#### 场景 4：按时间排序（即将过期优先）
```
- 机油 8 折【仅剩 2 天】（优先级高）
- 轮胎 7.5 折（优先级低）
```

触发条件：semantic_query 包含 "expiring" 或 sort_by="validity_end"

#### 场景 5：按金额排序（高优惠优先）
```
- 原厂配件 8.5 折（120 元优惠）
- 轮胎 7.5 折（80 元优惠）
- 机油 8 折（50 元优惠）
```

触发条件：semantic_query 包含 "discount_amount" 或 sort_by="discount_amount"

---

## apply_coupon 工具

**file**: `extensions/hlsc/tools/apply_coupon.py`

### Mock 数据

当 `MOCK_APPLY_COUPON=true` 或 `DATA_MANAGER_URL` 为空时，自动返回模拟的联系单：

```json
{
  "status": "success",
  "contact_order_id": "MOCK-ORD-{activity_id}-{shop_id}",
  "shop_name": "xxx",
  "activity_name": "xxx",
  "visit_time": "用户指定的到店时间",
  "message": "联系单已生成，商家会收到您的到店预约信息"
}
```

---

## 快速测试

### 1. 启动服务

```bash
cd mainagent
uv run python server.py
```

### 2. 测试 search_coupon 返回优惠列表

```bash
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-001",
    "user_id": "user123",
    "message": "我要找保养优惠，要支付宝支付的，送洗车就更好了"
  }'
```

**预期**：Agent 会调用 search_coupon，返回商户优惠卡片（CouponCard）

### 3. 测试 apply_coupon 申领优惠

继续对话：
```json
{
  "message": "帮我申请第一个（机油 8 折），周三下午 2 点"
}
```

**预期**：Agent 确认时间后调用 apply_coupon，返回联系单编号

---

## 测试场景清单（用于 #4 测试设计）

- [ ] 有优惠（单条、多条、对比）
- [ ] 无优惠（降级介绍平台 9 折）
- [ ] 申领优惠（确认时间 → 生成联系单）
- [ ] 转预订（用户申领后问"接下来怎么办"）
- [ ] 按优惠额排序
- [ ] 即将过期优先提示
- [ ] semantic_query 漏提取偏好（验证提示词有效性）

---

## 常见问题

**Q: 如何切换到不同的数据场景？**

A: 修改 `mock_data_server.py` 中的返回逻辑，或通过 semantic_query 参数触发不同场景（见上方描述）。

**Q: 生产环境如何关闭 mock？**

A: 
```env
DATA_MANAGER_URL=http://actual-datamanager-url:50400
MOCK_SEARCH_COUPON=false
MOCK_APPLY_COUPON=false
```

**Q: 如何验证 mock 数据正确？**

A: 查看 mainagent 日志和 mock 服务器日志（方案 B）。

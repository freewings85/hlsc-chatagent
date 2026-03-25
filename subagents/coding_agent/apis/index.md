# 业务 API 索引

目标：
- 帮你快速判断当前任务该读哪份 API 文档
- 帮你理解每类 API 解决什么问题
- 帮你拿到更适合任务结果组织的数据结构

原则：
- 只读当前任务真正需要的文档，不要把整个 `/apis` 目录都读一遍
- 优先按“任务”选文档，不要先按“后端接口名”选文档
- 返回结果优先组织成业务结果，不要直接回传后端原始大对象

## 统一命名

这组文档统一使用下面这些业务命名：

- `project_id / project_ids`：业务里的项目 id
- `car_model_id`：业务里的车型 id
- `shop_id / shop_ids`：商户 id
- `user_id`：用户 id
- `shop_type_id / shop_type_ids`：商户类型 id
- `primary_part_id / primary_part_ids`：标准词 / 标准配件 id
- `source_project_id / source_project_ids`：另一套上游项目 id，仅在做映射时使用

如果某个真实接口暂时还在使用旧命名，那只是实现细节；在这些文档里统一按上面的业务命名理解和组织。

## 按任务选择文档

### 一、商户相关

适用场景：
- 搜索附近商户
- 根据已有商户 id 补商户详情
- 查用户历史商户
- 理解商户类型差异

读取顺序：
- 标准商户搜索 / 商户详情：
  - `/apis/shops/search.md`
- 用户历史商户：
  - `/apis/shops/history.md`
- 商户类型知识：
  - `/apis/shops/types.md`

### 二、项目相关

适用场景：
- 从用户描述里匹配项目
- 查项目树 / 项目分类
- 查项目详情
- 查项目关系、历史项目、待服务项目

读取顺序：
- 项目检索：
  - `/apis/projects/search.md`
- 项目树 / 项目目录：
  - `/apis/projects/catalog.md`
- 项目详情：
  - `/apis/projects/details.md`
- 项目关系 / 用户项目历史：
  - `/apis/projects/relations.md`

### 三、报价相关

适用场景：
- 查附近商户报价
- 比较哪家更便宜
- 查行业参考价
- 查轮胎报价

读取顺序：
- 附近商户报价 / 价格比较：
  - `/apis/quotations/nearby_shops.md`
- 行情参考价 / 轮胎报价：
  - `/apis/quotations/market_reference.md`

获取所有商户类型列表，返回每种类型的 typeId 和名称。

无需参数，直接调用即可获取完整的商户类型列表。

使用场景：
- 用户按商户类型搜索附近商户时（如"找附近的4S店"、"综合修理厂"），先调用此工具获取 typeId
- 拿到 typeId 后，将其传给 search_nearby_shops 的 commercial_type 参数进行筛选

IMPORTANT: 当用户提到具体的商户类型名称时，必须先调用此工具查询对应的 typeId，不要猜测 typeId 的值。
Description:
收集用户自身所在位置。触发前端定位/选点界面，返回用户选择的地址和经纬度。

Usage notes:
- 仅在需要用户实时位置（如"附近""最近的"且无地名修饰）、且 context 中没有已知定位时使用。
- 不要用于解析用户指定的目标地址——目标地址直接传给 search_shops/search_coupon 的 location_text。

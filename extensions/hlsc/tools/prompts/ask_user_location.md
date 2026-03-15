向用户请求提供位置信息（经纬度），通过弹框让用户定位或选择位置。

当需要 lon/lat 但 request_context 中未设置、且用户也未提到任何位置时，调用此工具。
用户完成定位后返回 address、lat、lng。

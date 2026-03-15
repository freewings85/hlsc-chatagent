向用户请求提供车辆信息（car_model_id），通过弹框让用户选择或录入车型。

当需要 car_model_id 但 request_context 中未设置、且用户也未提到任何车型时，调用此工具。
用户完成选择后返回 car_model_id 和 car_model_name。

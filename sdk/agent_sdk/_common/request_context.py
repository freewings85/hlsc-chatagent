"""RequestContext + ContextFormatter：请求上下文基类和格式化接口。

业务层继承 RequestContext 扩展字段（如位置、车辆信息等）。
业务层继承 ContextFormatter 实现自定义格式化（注入 LLM 的文本）。
"""

import abc

from pydantic import BaseModel


class RequestContext(BaseModel):
    """请求上下文基类。业务继承扩展字段。"""


class ContextFormatter(abc.ABC):
    """上下文格式化接口。

    将 RequestContext 格式化为注入 LLM 的文本。
    每次 LLM 调用前都会执行，确保 LLM 始终能看到当前上下文。
    """

    @abc.abstractmethod
    def format(self, context: RequestContext) -> str:
        """将上下文格式化为自然语言文本。

        返回空字符串表示不注入。
        """
        ...

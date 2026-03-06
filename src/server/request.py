"""请求/响应模型"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """对话请求"""

    session_id: str
    message: str
    user_id: str = "anonymous"

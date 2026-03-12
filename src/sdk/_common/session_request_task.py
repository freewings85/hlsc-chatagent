"""会话请求任务"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.sdk._common.event_sinker import EventSinker

if TYPE_CHECKING:
    from src.sdk._common.request_context import RequestContext


@dataclass
class SessionRequestTask:
    """队列中的任务对象，携带 sinker 引用。"""

    session_id: str
    message: str
    user_id: str
    sinker: EventSinker
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    cancelled: bool = False
    context: RequestContext | None = None

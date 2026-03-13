"""PostgreSQL 存储后端实现（stub）"""

from agent_sdk._common.filesystem_backend import BackendProtocol


class PgBackend(BackendProtocol):
    """基于 PostgreSQL 的 BackendProtocol 实现。

    后续实现参考 langchain deepagents StoreBackend。
    """

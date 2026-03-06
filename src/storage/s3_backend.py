"""S3/MinIO 对象存储后端实现（stub）"""

from src.common.filesystem_backend import BackendProtocol


class S3Backend(BackendProtocol):
    """基于 S3/MinIO 的 BackendProtocol 实现。

    后续实现参考 langchain deepagents S3Backend。
    """

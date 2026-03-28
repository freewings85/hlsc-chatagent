"""业务地图节点模型"""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class BusinessChildRef(BaseModel):
    """业务地图子节点引用（YAML 中 children 列表的每一项）"""

    id: str
    name: str
    keywords: list[str] = []
    path: str | None = None
    optional: bool = False
    depends_on: list[str] = []


class BusinessNode(BaseModel):
    """业务地图节点（对应一个 YAML 文件的完整内容）"""

    id: str
    name: str

    # ── 业务定义字段（给 MainAgent 看的）──
    description: str | None = None
    checklist: list[str] | None = None
    output: list[str] | None = None
    depends_on: list[str] | None = None
    cancel_directions: dict[str, str] | None = None

    # ── 导航结构字段（给小模型 Agent 和代码层用的）──
    keywords: list[str] = []
    children: list[BusinessChildRef] | None = None
    optional: bool = False

    # ── 运行时字段（不从 YAML 读取，加载时填充）──
    parent_id: str | None = None
    resolved_children: list[BusinessNode] = []

    @model_validator(mode="after")
    def _check_has_business_content(self) -> BusinessNode:
        """description 和 checklist 不能同时为空，每个节点必须有实质业务内容。"""
        if not self.description and not self.checklist:
            raise ValueError(
                f"节点 '{self.id}' 的 description 和 checklist 不能同时为空"
            )
        return self

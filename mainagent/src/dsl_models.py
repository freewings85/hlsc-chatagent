"""DSL 数据模型：planagent（/plan 端点）的输出 schema。

一个 Plan 就是一个 DAG，节点声明依赖关系。变量传递走「共享 context bag」——
DSL 只管拓扑，不管数据流；每个 action 自己从累积的 context 里取需要的字段。

**术语约定**：
- 对 LLM 和调用方（orchestrator）暴露的概念叫 **action**（中文「动作」）
- 后端 workflows 侧的 Temporal activity 是 action 的具体实现，但 planagent
  侧完全不感知这一点。action 的值就是一个字符串名，由 orchestrator 负责
  把它映射到具体的 Temporal activity

初版约束（刻意放宽，跑通闭环优先）：
- initial_inputs 是自由 dict，不强 schema
- depends_on 里的 id 必须在 nodes 内存在（Pydantic 侧做图完整性校验）
- 不检查是否有环（DSL 解释器跑时自然会死锁/错误，先不在入口强制）
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Node(BaseModel):
    """DAG 中的一个节点 —— 一次待执行的 action。"""

    id: str
    """节点唯一 id（DSL 内唯一，用来在 depends_on 里引用）。"""

    action: str
    """动作名，必须在请求传入的 available_actions 白名单内。"""

    depends_on: list[str] = Field(default_factory=list)
    """前驱节点 id 列表。为空 = 可作为根节点并行执行。"""


class Plan(BaseModel):
    """规划器输出的完整 DSL。"""

    plan_id: str
    """规划 id，planagent 侧生成，用于追踪。"""

    nodes: list[Node]
    """DAG 节点列表。"""

    initial_inputs: dict[str, Any] = Field(default_factory=dict)
    """DAG 入口注入的初始变量（user_query / session_id / user_id 等）。"""

    @model_validator(mode="after")
    def _validate_graph(self) -> Plan:
        """图完整性：depends_on 里引用的 id 必须在 nodes 里存在，id 不重复。"""
        node_ids: set[str] = {n.id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Plan.nodes 里存在重复 id")

        for n in self.nodes:
            for dep in n.depends_on:
                if dep not in node_ids:
                    raise ValueError(
                        f"节点 {n.id!r} 的 depends_on 引用了不存在的 id {dep!r}"
                    )
        return self


class ActionDef(BaseModel):
    """请求侧传入的一条 action 描述。

    orchestrator 在 `/plan` 请求的 context.available_actions 里传入整列。
    planagent 把它们渲染成 markdown 表格拼进 system prompt，让 LLM 看到白名单。
    """

    name: str
    desc: str = ""

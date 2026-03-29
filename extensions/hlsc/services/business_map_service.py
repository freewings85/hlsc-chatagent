"""业务地图服务：从配置路径加载 YAML 到内存，提供查询和组装能力。

各进程在 settings 中配置 YAML 路径，启动时调用 ``load()``。
"""

from __future__ import annotations

import logging
from pathlib import Path

from hlsc.business_map.loader import BusinessMap
from hlsc.business_map.model import BusinessChildRef, BusinessNode

logger: logging.Logger = logging.getLogger(__name__)


class BusinessMapService:
    """业务地图服务"""

    def __init__(self) -> None:
        self._map: BusinessMap | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def load(self, root_dir: str | Path) -> None:
        """加载 YAML 目录树到内存。"""
        self._map = BusinessMap.load(root_dir)

    @property
    def is_loaded(self) -> bool:
        """是否已加载业务地图。"""
        return self._map is not None

    @property
    def _biz_map(self) -> BusinessMap:
        """内部访问，未加载时抛异常。"""
        if self._map is None:
            raise RuntimeError("BusinessMap 尚未加载，请先调用 load()")
        return self._map

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def find(self, node_id: str) -> BusinessNode:
        """按 ID 查找节点，不存在抛 KeyError。"""
        return self._biz_map.find(node_id)

    def path_from_root(self, node_id: str) -> list[BusinessNode]:
        """从根到该节点的完整路径（含根和自身）。"""
        node: BusinessNode = self._biz_map.find(node_id)
        return self._biz_map.path_from_root(node)

    # ------------------------------------------------------------------
    # 给小模型 Agent 用：只返回导航字段
    # ------------------------------------------------------------------

    def get_business_children_nav(self, node_id: str) -> str:
        """返回指定节点的子节点导航摘要（id/name/keywords/children 概览）。

        只包含导航结构字段，不包含 description/checklist/output 等业务定义。
        """
        node: BusinessNode = self._biz_map.find(node_id)
        if not node.children:
            return f"节点 '{node.name}'（{node.id}）没有子节点。"

        lines: list[str] = [f"# {node.name} 的子节点"]
        child_ref: BusinessChildRef
        for child_ref in node.children:
            parts: list[str] = [f"- {child_ref.name}（{child_ref.id}）"]
            if child_ref.keywords:
                parts.append(f"  关键词: {', '.join(child_ref.keywords)}")
            if child_ref.optional:
                parts.append("  [可选]")
            if child_ref.depends_on:
                parts.append(f"  依赖: {', '.join(child_ref.depends_on)}")
            # 如果子节点已解析且自身还有 children，标注"含子节点"
            resolved_child: BusinessNode | None = self._try_find(child_ref.id)
            if resolved_child is not None and resolved_child.children:
                child_count: int = len(resolved_child.children)
                parts.append(f"  含 {child_count} 个子节点")
            lines.extend(parts)

        return "\n".join(lines)

    def get_business_node_nav(self, node_id: str) -> str:
        """返回单个节点的导航信息（id/name/keywords/children 概览）。

        只包含导航结构字段，不包含业务定义。
        """
        node: BusinessNode = self._biz_map.find(node_id)
        lines: list[str] = [f"# {node.name}（{node.id}）"]
        if node.keywords:
            lines.append(f"关键词: {', '.join(node.keywords)}")
        if node.optional:
            lines.append("[可选]")
        if node.children:
            lines.append(f"子节点数: {len(node.children)}")
            child_ref: BusinessChildRef
            for child_ref in node.children:
                entry: str = f"  - {child_ref.name}（{child_ref.id}）"
                if child_ref.keywords:
                    entry += f" [{', '.join(child_ref.keywords)}]"
                lines.append(entry)
        else:
            lines.append("叶节点（无子节点）")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 给 MainAgent 用：返回完整业务定义 Markdown
    # ------------------------------------------------------------------

    def get_business_node_detail(self, node_id: str) -> str:
        """返回从根到指定节点的完整路径切片 Markdown。

        包含路径上每个节点的所有业务定义字段。
        """
        path: list[BusinessNode] = self.path_from_root(node_id)
        depth: int = len(path) - 1
        header: str = f"定位深度：{depth}"
        sections: list[str] = [header]

        node: BusinessNode
        for node in path:
            sections.append(self.format_node(node))

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # 代码层组装
    # ------------------------------------------------------------------

    def assemble_slice(self, node_ids: list[str]) -> str:
        """根据节点 ID 列表，组装从根到每个节点的完整路径切片。

        组装逻辑：
        1. 过滤无效 ID（日志警告，跳过）
        2. 对每个有效 node_id，获取从根到该节点的路径
        3. 路径上的祖先节点去重（seen_ids），只输出一次
        4. 不同路径之间用 ``---`` 分隔
        5. 定位深度取所有路径中的最大深度
        6. 多路径时标题追加 ``（多路径）``
        """
        # 1. 过滤无效 ID
        valid_ids: list[str] = []
        node_id: str
        for node_id in node_ids:
            found: BusinessNode | None = self._try_find(node_id)
            if found is None:
                logger.warning("assemble_slice: 忽略无效节点 ID '%s'", node_id)
            else:
                valid_ids.append(node_id)

        if not valid_ids:
            return ""

        # 2-3. 对每个有效 ID，获取路径并去重组装
        target_ids: set[str] = set(valid_ids)
        seen_ids: set[str] = set()
        sections: list[str] = []

        i: int
        for i, node_id in enumerate(valid_ids):
            path: list[BusinessNode] = self.path_from_root(node_id)
            ancestor: BusinessNode
            for ancestor in path:
                if ancestor.id in seen_ids:
                    continue
                seen_ids.add(ancestor.id)
                # 跳过根节点的 description（元数据，不是业务指引）
                if ancestor.id == "root":
                    continue
                # 目标节点标注 ← 当前定位
                is_target: bool = ancestor.id in target_ids
                sections.append(self.format_node(ancestor, is_target=is_target))

            # 不同路径之间用 "---" 分隔（最后一条路径后不加）
            if i < len(valid_ids) - 1:
                sections.append("---")

        # 4. 组装头部：标明当前定位的节点名称
        target_names: list[str] = [self.find(nid).name for nid in valid_ids]
        header: str = f"当前定位：{'、'.join(target_names)}"

        return header + "\n\n" + "\n\n".join(sections)

    def format_node(self, node: BusinessNode, *, is_target: bool = False) -> str:
        """把单个节点的 YAML 内容格式化为一段 Markdown。

        格式：
        - ``### {node.name}`` 标题（目标节点追加 ← 当前定位）
        - description（去除首尾空白）
        - 待办：checklist 列表
        - 产出：output 列表
        - 依赖：depends_on 列表
        - 取消走向：cancel_directions（reason → direction）
        """
        title: str = f"### {node.name}"
        if is_target:
            title += " ← 当前定位"
        parts: list[str] = [title]

        if node.description:
            parts.append(node.description.strip())
        if node.checklist:
            parts.append("待办：")
            item: str
            for item in node.checklist:
                parts.append(f"- {item}")
        if node.output:
            parts.append("产出：")
            item2: str
            for item2 in node.output:
                parts.append(f"- {item2}")
        if node.depends_on:
            parts.append("依赖：")
            dep: str
            for dep in node.depends_on:
                parts.append(f"- {dep}")
        if node.cancel_directions:
            parts.append("取消走向：")
            reason: str
            direction: str
            for reason, direction in node.cancel_directions.items():
                parts.append(f"- {reason} → {direction}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _try_find(self, node_id: str) -> BusinessNode | None:
        """尝试查找节点，不存在返回 None。"""
        try:
            return self._biz_map.find(node_id)
        except KeyError:
            return None


business_map_service: BusinessMapService = BusinessMapService()

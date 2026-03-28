"""业务地图加载器：递归加载 YAML 目录树，构建索引"""

from __future__ import annotations

from pathlib import Path

import yaml

from hlsc.business_map.model import BusinessChildRef, BusinessNode


class BusinessMap:
    """业务地图：加载 YAML 目录树，提供查找和路径计算。

    YAML 目录约定：
    - 有子节点 -> 用目录，里面放 ``_node.yaml``
    - 没子节点 -> 直接是 ``.yaml`` 文件
    """

    def __init__(self, root: BusinessNode, index: dict[str, BusinessNode]) -> None:
        self._root: BusinessNode = root
        self._index: dict[str, BusinessNode] = index

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, root_dir: str | Path) -> BusinessMap:
        """递归加载 YAML 目录树。

        加载规则：
        1. 读 ``_root.yaml`` 作为根节点
        2. 对每个 child：
           - ``path`` 以 ``/`` 结尾 -> 目录节点，读 ``{path}_node.yaml``
           - ``path`` 是 ``.yaml`` 文件 -> 叶节点文件
           - ``path`` 为 ``None`` -> 从 child.id 推导文件名 ``{id-with-hyphens}.yaml``
        3. 构建 id -> node 索引，校验 ID 唯一
        4. 设置 ``parent_id`` 和 ``resolved_children``
        """
        root_path: Path = Path(root_dir)
        root_file: Path = root_path / "_root.yaml"
        if not root_file.exists():
            raise FileNotFoundError(f"找不到根文件: {root_file}")

        index: dict[str, BusinessNode] = {}
        root_node: BusinessNode = _load_node_recursive(root_path, root_file, index, parent_id=None)
        return cls(root=root_node, index=index)

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------

    @property
    def root(self) -> BusinessNode:
        """根节点"""
        return self._root

    def find(self, node_id: str) -> BusinessNode:
        """按 ID 查找节点，不存在抛 KeyError。"""
        if node_id not in self._index:
            raise KeyError(f"节点 ID 不存在: {node_id}")
        return self._index[node_id]

    def path_from_root(self, node: BusinessNode) -> list[BusinessNode]:
        """从根到该节点的完整路径（含根和自身）。"""
        path: list[BusinessNode] = []
        current: BusinessNode | None = node
        while current is not None:
            path.append(current)
            if current.parent_id is not None:
                current = self._index[current.parent_id]
            else:
                current = None
        path.reverse()
        return path

    def all_ids(self) -> set[str]:
        """返回所有已加载节点的 ID 集合。"""
        return set(self._index.keys())


# ======================================================================
# 内部递归加载
# ======================================================================


def _id_to_filename(node_id: str) -> str:
    """将 node id（下划线风格）转为文件名（连字符风格 + .yaml）。

    例: ``fuzzy_intent`` -> ``fuzzy-intent.yaml``
    """
    return node_id.replace("_", "-") + ".yaml"


def _load_yaml(file_path: Path) -> dict:
    """读取并解析单个 YAML 文件。"""
    with open(file_path, "r", encoding="utf-8") as f:
        data: dict = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML 文件格式错误（应为 dict）: {file_path}")
    return data


def _register_node(node: BusinessNode, index: dict[str, BusinessNode]) -> None:
    """将节点注册到索引，校验 ID 唯一。"""
    if node.id in index:
        raise ValueError(f"重复的节点 ID: {node.id}")
    index[node.id] = node


def _load_node_recursive(
    base_dir: Path,
    yaml_file: Path,
    index: dict[str, BusinessNode],
    parent_id: str | None,
) -> BusinessNode:
    """递归加载一个节点及其所有子节点。

    Args:
        base_dir: 当前节点所在的目录（用于解析子节点的相对路径）
        yaml_file: 当前节点的 YAML 文件路径
        index: 全局 id -> node 索引（就地修改）
        parent_id: 父节点 ID（根节点为 None）

    Returns:
        加载完成的 BusinessNode（已设置 parent_id 和 resolved_children）
    """
    raw: dict = _load_yaml(yaml_file)
    node: BusinessNode = BusinessNode(**raw, parent_id=parent_id)
    _register_node(node, index)

    if node.children is None:
        return node

    # 解析每个 child ref，加载对应的子节点
    resolved: list[BusinessNode] = []
    child_ref: BusinessChildRef
    for child_ref in node.children:
        child_node: BusinessNode = _load_child(base_dir, child_ref, index, parent_id=node.id)
        resolved.append(child_node)

    node.resolved_children = resolved
    return node


def _load_child(
    base_dir: Path,
    child_ref: BusinessChildRef,
    index: dict[str, BusinessNode],
    parent_id: str,
) -> BusinessNode:
    """根据 BusinessChildRef 加载子节点。

    路径解析规则：
    - path 以 '/' 结尾 -> 目录节点，读 {base_dir}/{path}_node.yaml
    - path 是 .yaml 文件 -> 叶节点，读 {base_dir}/{path}
    - path 为 None -> 从 id 推导：{base_dir}/{id-with-hyphens}.yaml
    """
    if child_ref.path is not None and child_ref.path.endswith("/"):
        # 目录节点
        child_dir: Path = base_dir / child_ref.path
        child_file: Path = child_dir / "_node.yaml"
        return _load_node_recursive(child_dir, child_file, index, parent_id=parent_id)
    elif child_ref.path is not None and child_ref.path.endswith(".yaml"):
        # 显式指定的叶节点文件
        child_file = base_dir / child_ref.path
        return _load_node_recursive(base_dir, child_file, index, parent_id=parent_id)
    else:
        # path 为 None，从 id 推导文件名
        filename: str = _id_to_filename(child_ref.id)
        child_file = base_dir / filename
        return _load_node_recursive(base_dir, child_file, index, parent_id=parent_id)

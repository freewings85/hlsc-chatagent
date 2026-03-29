"""将 AllTree.yaml 单文件格式转换为业务地图目录树格式。

用法：
    cd extensions/business-map
    python convert_tree.py AllTree.yaml output/

输入：AllTree.yaml（单文件，task_T1/T2/T3 顶层结构）
输出：目录树（_root.yaml + 子目录/文件），与 data/ 下现有格式一致

转换规则：
  - task_T1/T2/T3 → root 的 children 目录
  - checklist 内的子节点对象 → children 引用 + 独立文件/目录
  - NODE_T1_XXX 风格 ID → 去前缀的 snake_case（如 project_clarify）
  - cancel_directions 列表 → dict（reason: direction）
  - depends_on 归一化为 list[str]
  - 目录名用 kebab-case（id snake_case → kebab-case）
  - keywords 从 name 自动提取（可后续手动补充）
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


# ── YAML 输出配置 ──

class _LiteralStr(str):
    """标记为 YAML literal block scalar（|）的字符串。"""


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> Any:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_LiteralStr, _literal_representer)


# ── ID 转换 ──

def _normalize_id(raw_id: str) -> str:
    """保留原始 ID，仅转小写。

    示例：
      NODE_T1_PROJECT_CLARIFY → node_t1_project_clarify
      T1 → t1
    """
    return raw_id.lower()


def _id_to_dirname(node_id: str) -> str:
    """snake_case ID → kebab-case 目录/文件名。

    示例：project_clarify → project-clarify
    """
    return node_id.replace("_", "-")


# ── depends_on 归一化 ──

def _normalize_depends_on(raw: Any) -> list[str] | None:
    """将 depends_on 归一化为 list[str] 或 None。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped: str = raw.strip()
        return [stripped] if stripped else None
    if isinstance(raw, list):
        result: list[str] = [str(item).strip() for item in raw if item]
        return result if result else None
    return None


# ── cancel_directions 转换 ──

def _convert_cancel_directions(raw: Any) -> dict[str, str] | None:
    """将 cancel_directions 从列表转为 dict。

    源格式示例：
      - 若车主不愿提供，请查看：task_T4
    目标格式：
      车主不愿提供: 请查看 task_T4
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw

    result: dict[str, str] = {}
    item: Any
    for item in raw:
        text: str = str(item).strip()
        # 尝试解析 "若X，请查看：Y" 或 "若X，Y" 模式
        match: re.Match[str] | None = re.match(r"若(.+?)，(.+)", text)
        if match:
            reason: str = match.group(1).strip()
            direction: str = match.group(2).strip()
            # 清理 "请查看：" 前缀
            direction = re.sub(r"^请查看：\s*", "", direction)
            result[reason] = direction
        else:
            # 无法解析时，整条作为 key，value 留空
            result[text] = ""
    return result if result else None


# ── keywords 提取 ──

# 常见的业务关键词映射（name 关键词 → keywords 列表）
_KEYWORD_MAP: dict[str, list[str]] = {
    "养车项目": ["保养", "维修", "项目"],
    "梳理": ["梳理", "确认"],
    "搜索": ["搜索", "查找"],
    "车型": ["车型", "车架号", "VIN"],
    "车辆": ["车型", "车辆"],
    "报价": ["报价", "价格", "多少钱"],
    "省钱": ["省钱", "优惠", "便宜", "折扣"],
    "消费偏好": ["偏好", "省钱", "优惠"],
    "商户": ["商户", "门店", "找店"],
    "下单": ["下单", "预订", "预约"],
    "洗车": ["洗车"],
    "检测": ["检测", "检查"],
    "优惠券": ["优惠券", "券", "折扣"],
    "竞价": ["竞价", "比价", "报价"],
    "展示": ["展示", "查看"],
}


def _extract_keywords(name: str) -> list[str]:
    """从节点 name 中提取关键词。"""
    keywords: list[str] = []
    key: str
    values: list[str]
    for key, values in _KEYWORD_MAP.items():
        if key in name:
            kw: str
            for kw in values:
                if kw not in keywords:
                    keywords.append(kw)
    return keywords


# ── 节点解析 ──

class ParsedNode:
    """解析后的节点，包含子节点引用。"""

    def __init__(
        self,
        node_id: str,
        name: str,
        description: str | None,
        depends_on: list[str] | None,
        output: list[str] | None,
        cancel_directions: dict[str, str] | None,
        checklist_strings: list[str] | None,
        children: list[ParsedNode] | None,
        keywords: list[str],
    ) -> None:
        self.node_id: str = node_id
        self.name: str = name
        self.description: str | None = description
        self.depends_on: list[str] | None = depends_on
        self.output: list[str] | None = output
        self.cancel_directions: dict[str, str] | None = cancel_directions
        self.checklist_strings: list[str] | None = checklist_strings
        self.children: list[ParsedNode] | None = children
        self.keywords: list[str] = keywords

    @property
    def is_leaf(self) -> bool:
        return not self.children


def _parse_checklist_node(raw: dict[str, Any]) -> ParsedNode:
    """递归解析 checklist 中的子节点对象。"""
    raw_id: str = str(raw.get("id", ""))
    node_id: str = _normalize_id(raw_id)
    name: str = str(raw.get("name", ""))
    description: str | None = raw.get("description")
    depends_on: list[str] | None = _normalize_depends_on(raw.get("depends_on"))
    output: list[str] | None = raw.get("output")
    cancel_dirs: dict[str, str] | None = _convert_cancel_directions(raw.get("cancel_directions"))
    keywords: list[str] = _extract_keywords(name)

    # 检查 checklist 是否包含子节点对象
    raw_checklist: Any = raw.get("checklist")
    children: list[ParsedNode] | None = None
    checklist_strings: list[str] | None = None

    if isinstance(raw_checklist, list) and raw_checklist:
        first: Any = raw_checklist[0]
        if isinstance(first, dict) and "id" in first:
            # checklist 包含子节点对象 → 递归解析为 children
            children = [_parse_checklist_node(item) for item in raw_checklist]
            # 生成摘要 checklist 字符串
            checklist_strings = [child.name for child in children]
        elif isinstance(first, str):
            checklist_strings = raw_checklist

    return ParsedNode(
        node_id=node_id,
        name=name,
        description=description,
        depends_on=depends_on,
        output=output,
        cancel_directions=cancel_dirs,
        checklist_strings=checklist_strings,
        children=children,
        keywords=keywords,
    )


def _parse_task(raw: dict[str, Any]) -> ParsedNode:
    """解析顶层 task 节点。"""
    raw_id: str = str(raw.get("id", ""))
    node_id: str = _normalize_id(raw_id)
    name: str = str(raw.get("name", ""))
    description: str | None = raw.get("description")
    depends_on: list[str] | None = _normalize_depends_on(raw.get("depends_on"))
    output: list[str] | None = raw.get("output")
    cancel_dirs: dict[str, str] | None = _convert_cancel_directions(raw.get("cancel_directions"))
    keywords: list[str] = _extract_keywords(name)

    # 解析 checklist 中的子节点
    raw_checklist: Any = raw.get("checklist")
    children: list[ParsedNode] | None = None
    checklist_strings: list[str] | None = None

    if isinstance(raw_checklist, list) and raw_checklist:
        first: Any = raw_checklist[0]
        if isinstance(first, dict) and "id" in first:
            children = [_parse_checklist_node(item) for item in raw_checklist]
            checklist_strings = [child.name for child in children]

    return ParsedNode(
        node_id=node_id,
        name=name,
        description=description,
        depends_on=depends_on,
        output=output,
        cancel_directions=cancel_dirs,
        checklist_strings=checklist_strings,
        children=children,
        keywords=keywords,
    )


# ── YAML 文件生成 ──

def _build_node_yaml(node: ParsedNode) -> dict[str, Any]:
    """构建 _node.yaml 或叶节点 yaml 的 dict 内容。"""
    data: dict[str, Any] = {
        "id": node.node_id,
        "name": node.name,
    }

    if node.description:
        desc: str = node.description.strip()
        if "\n" in desc:
            data["description"] = _LiteralStr(desc + "\n")
        else:
            data["description"] = desc

    if node.depends_on:
        data["depends_on"] = node.depends_on

    if node.checklist_strings:
        data["checklist"] = node.checklist_strings

    if node.output:
        data["output"] = node.output

    if node.cancel_directions:
        data["cancel_directions"] = node.cancel_directions

    if node.children:
        children_refs: list[dict[str, Any]] = []
        child: ParsedNode
        for child in node.children:
            ref: dict[str, Any] = {
                "id": child.node_id,
                "name": child.name,
            }
            if child.keywords:
                ref["keywords"] = child.keywords
            if not child.is_leaf:
                ref["path"] = _id_to_dirname(child.node_id) + "/"
            if child.depends_on:
                ref["depends_on"] = child.depends_on
            children_refs.append(ref)
        data["children"] = children_refs

    return data


def _write_yaml(data: dict[str, Any], file_path: Path) -> None:
    """写入 YAML 文件。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )
    print(f"  写入: {file_path}")


def _write_node_recursive(node: ParsedNode, base_dir: Path) -> None:
    """递归写入节点到目录树。"""
    if node.is_leaf:
        # 叶节点 → 直接写 .yaml 文件
        filename: str = _id_to_dirname(node.node_id) + ".yaml"
        file_path: Path = base_dir / filename
        data: dict[str, Any] = _build_node_yaml(node)
        _write_yaml(data, file_path)
    else:
        # 有子节点 → 创建目录 + _node.yaml
        dir_name: str = _id_to_dirname(node.node_id)
        node_dir: Path = base_dir / dir_name
        node_dir.mkdir(parents=True, exist_ok=True)

        data = _build_node_yaml(node)
        _write_yaml(data, node_dir / "_node.yaml")

        # 递归写入每个子节点
        child: ParsedNode
        for child in node.children:  # type: ignore[union-attr]
            _write_node_recursive(child, node_dir)


# ── 主入口 ──

def convert(input_file: Path, output_dir: Path) -> None:
    """执行转换：AllTree.yaml → 目录树。"""
    print(f"读取: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    meta: dict[str, Any] = raw.get("meta", {})
    print(f"业务地图: {meta.get('name', '未命名')} v{meta.get('version', '?')}")

    # 解析所有 task 节点
    tasks: list[ParsedNode] = []
    key: str
    value: Any
    for key, value in raw.items():
        if key.startswith("task_") and isinstance(value, dict):
            task: ParsedNode = _parse_task(value)
            tasks.append(task)
            print(f"  解析 task: {key} → id={task.node_id}, children={len(task.children or [])}")

    if not tasks:
        print("错误: 未找到任何 task 节点")
        sys.exit(1)

    # 构建 root 节点
    root_description: str = meta.get("description", "")
    root_data: dict[str, Any] = {
        "id": "root",
        "name": meta.get("name", "业务地图"),
    }
    if root_description:
        root_data["description"] = _LiteralStr(root_description.strip() + "\n")

    root_children: list[dict[str, Any]] = []
    task_node: ParsedNode
    for task_node in tasks:
        ref: dict[str, Any] = {
            "id": task_node.node_id,
            "name": task_node.name,
        }
        if task_node.keywords:
            ref["keywords"] = task_node.keywords
        if task_node.depends_on:
            ref["depends_on"] = task_node.depends_on
        ref["path"] = _id_to_dirname(task_node.node_id) + "/"
        root_children.append(ref)
    root_data["children"] = root_children

    # 清空输出目录
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 写入 _root.yaml
    _write_yaml(root_data, output_dir / "_root.yaml")

    # 写入每个 task 的目录树
    for task_node in tasks:
        if task_node.is_leaf:
            filename = _id_to_dirname(task_node.node_id) + ".yaml"
            _write_yaml(_build_node_yaml(task_node), output_dir / filename)
        else:
            task_dir: Path = output_dir / _id_to_dirname(task_node.node_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            _write_yaml(_build_node_yaml(task_node), task_dir / "_node.yaml")
            child: ParsedNode
            for child in task_node.children:  # type: ignore[union-attr]
                _write_node_recursive(child, task_dir)

    print(f"\n转换完成! 输出目录: {output_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python convert_tree.py <AllTree.yaml> [output_dir]")
        print("  output_dir 默认为 ./output")
        sys.exit(1)

    input_path: Path = Path(sys.argv[1])
    output_path: Path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output")

    if not input_path.exists():
        print(f"错误: 文件不存在 {input_path}")
        sys.exit(1)

    convert(input_path, output_path)

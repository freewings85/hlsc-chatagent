# 决策树可视化工具

将 `scene_config_example.yaml` 中定义的决策树和场景配置以树形图方式可视化展示。

## 快速开始

由于页面通过 `fetch` 加载 YAML 文件，需要通过 HTTP 服务器打开（直接双击 `index.html` 会因 CORS 限制无法加载文件）。

```bash
# 在 extensions/business-map 目录下启动服务
cd extensions/business-map
python -m http.server 8080

# 浏览器打开
# http://localhost:8080/visualizer/
```

## 功能说明

### 树形图

- **根节点**（顶部）：决策入口
- **蓝色节点**：条件判断节点，显示 `if` 条件或 label
- **绿色节点**：有条件的场景叶节点，显示 scene ID + 场景名称
- **黄色节点**：兜底节点（无 `if` 条件的 fallback 场景）
- **连线**：从父节点到子节点的贝塞尔曲线

### 交互

- **鼠标悬停**：任意节点弹出 tooltip，显示条件、目标、工具等摘要
- **点击叶节点**：右侧面板展示完整场景定义（goal、target_slots、tools、exit_when、strategy）
- **点击条件节点**：右侧面板展示条件详情和子节点数
- **缩放**：鼠标滚轮缩放
- **平移**：鼠标拖拽移动画布
- **点击空白区域**：取消选中，隐藏详情

### 阶段信息

页面顶部显示 S1、S2 阶段卡片，列出每个阶段需要收集的槽位。

## 技术栈

- **D3.js v7**（CDN）：树形布局和 SVG 渲染
- **js-yaml v4**（CDN）：前端解析 YAML 文件
- 纯前端，无需构建工具，单文件 `index.html`

## 数据来源

页面加载时通过 `fetch("../scene_config_example.yaml")` 读取同目录上级的配置文件。修改 YAML 后刷新页面即可看到最新的决策树。

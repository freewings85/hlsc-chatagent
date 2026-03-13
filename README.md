# 话痨说车对话 Agent

## 项目结构

```
sdk/                    # Agent SDK（独立 Python 包：agent_sdk）
mainagent/              # 话痨说车主 Agent（独立项目）
subagents/
  price_finder/         # 比价 Subagent（独立项目）
web/                    # 公用前端（React + Vite）
```

每个目录是独立的 Python 项目，有各自的 `pyproject.toml` 和 `tests/`。根目录的 `pyproject.toml` 将所有子项目作为依赖统一管理。

## 首次配置

### 1. 安装所有依赖

```bash
uv sync                                    # 在根目录执行，一次性安装 SDK + 所有 Agent 的依赖
```

### 2. 启动 MainAgent

```bash
cd mainagent
uv run python server.py                    # 端口 8100
```

### 3. 启动 PriceFinder Subagent

```bash
cd subagents/price_finder
uv run python server.py                    # 端口 8101
```

### 4. 启动前端

```bash
cd web
npm install
npm run dev                                # 连接 MainAgent → localhost:3100
```

连接不同后端：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8101 VITE_PORT=3101 npm run dev
```

### 5. 前置依赖

- **Temporal Server**（interrupt 机制）：`TEMPORAL_ENABLED=true`
- **Nacos**（生产配置中心）：本地开发用 `USE_NACOS=FALSE`

## VS Code

F5 启动，选择 **MainAgent** 或 **PriceFinder** 配置。

## 运行测试

各项目在自己目录下运行：

```bash
cd sdk && uv run pytest tests/ -v
cd mainagent && uv run pytest tests/ -v
```

## 各项目说明

- [SDK README](sdk/README.md)
- [MainAgent README](mainagent/README.md)
- [PriceFinder README](subagents/price_finder/README.md)

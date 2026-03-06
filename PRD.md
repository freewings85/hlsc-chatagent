# ChatAgent PRD — Phase 1: 最小可运行 Agent Loop

## 项目定位

通用对话 Agent，类似 Claude Code 的架构思路：
- 用户输入 → Agent 自主多步工具调用 → 流式返回结果
- 基于 Pydantic AI，但流程控制权完全在自己手里

## 技术栈

- **框架**: Pydantic AI（Agent + iter/next + deps + DynamicToolset + provider 抽象）
- **API**: FastAPI + SSE
- **持久化**: 文件系统（消息历史、会话状态）
- **环境**: Python 3.12 + uv
- **测试**: pytest + FunctionModel mock

## 代码规范（强制）

**Java 级别的类型严格性**：所有变量、函数参数/返回值、类字段都必须声明类型，无例外。

```python
# 变量
name: str = "hello"
items: list[str] = []
result: AgentDeps | None = None

# 函数
async def get_weather(ctx: RunContext[AgentDeps], city: str) -> str:

# 类
@dataclass
class AgentDeps:
    session_id: str = "default"
    tool_map: dict[str, ToolFunc] = field(default_factory=dict)

# 类型别名
ToolFunc = Callable[..., str]
```

使用 `uv run mypy src/` 检查，必须通过。详见 `CLAUDE.md`。

## 架构决策

1. **Agent loop 手动驱动** — 用 `agent.iter()` + `run.next(node)` 逐步控制，不用 `async for` 自动迭代
2. **工具动态注册** — `DynamicToolset(per_run_step=True)`，通过 deps 控制每步可用工具
3. **消息持久化用文件系统** — 参考 Claude Code，JSON 文件存 message_history
4. **不用 @agent.tool** — Tool 函数独立定义，通过 `RunContext[Deps]` 获取依赖

## 核心模式（已验证，见 pydantic-test/pydantic_main_loop.py）

整个 agent 的构建围绕以下骨架展开，所有功能都在这个结构上扩展：

```python
from typing import Callable
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.agent import ModelRequestNode, CallToolsNode
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.toolsets._dynamic import DynamicToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_graph import End

ToolFunc = Callable[..., str]

# ---- Deps：所有状态通过依赖注入传递 ----
@dataclass
class AgentDeps:
    session_id: str
    user_id: str
    available_tools: list[str]          # 控制当前可用工具
    tool_map: dict[str, ToolFunc]       # tool 名 → 实现函数（eval 时可替换）
    tool_call_count: int = 0            # tool 执行过程中可修改的状态

# ---- Tool 函数：独立定义，通过 RunContext 访问 deps ----
async def get_weather(ctx: RunContext[AgentDeps], city: str) -> str:
    """获取天气"""  # docstring 作为 tool description
    ctx.deps.tool_call_count += 1       # 可修改 deps 状态
    return f"{city}: 晴天 25°C"

# ---- DynamicToolset：每步从 deps 读取工具集 ----
def get_tools(ctx: RunContext[AgentDeps]) -> FunctionToolset:
    toolset = FunctionToolset()
    for name in ctx.deps.available_tools:
        if name in ctx.deps.tool_map:
            toolset.add_tool(Tool(ctx.deps.tool_map[name], name=name))
    return toolset

# ---- history_processor：每次调 LLM 前修改消息 ----
def my_processor(messages: list[ModelMessage]) -> list[ModelMessage]:
    return messages

# ---- Agent 工厂：model 可替换（eval 时传 FunctionModel）----
def create_agent(model: Model | None = None) -> Agent:
    return Agent(
        model or real_model,
        deps_type=AgentDeps,
        system_prompt="...",
        toolsets=[DynamicToolset(get_tools, per_run_step=True)],
        history_processors=[my_processor],
    )

# ---- 核心循环：手动 iter/next，每步可插入逻辑 ----
async def run_agent(agent: Agent, user_input: str, deps: AgentDeps) -> dict:
    async with agent.iter(user_input, deps=deps) as run:
        node = run.next_node                    # 拿到第一个 node，未执行

        while not isinstance(node, End):
            if isinstance(node, ModelRequestNode):
                # 调 LLM 前：可修改 deps（动态加工具、改状态）
                deps.available_tools.append("new_tool")

            elif isinstance(node, CallToolsNode):
                # LLM 返回后：可观察响应、发 SSE
                for part in node.model_response.parts:
                    ...

            node = await run.next(node)         # 执行当前 node，拿到下一个
```

### 关键约束（踩坑总结）

- **mock tool 必须带 `RunContext[AgentDeps]` 类型注解**，否则 Pydantic AI 不识别 ctx 参数
- **用 `Tool(func, name=name)` 显式指定 tool name**，不依赖函数名匹配
- **`next(node)` 是黑盒边界**：在 `next()` 前改 deps，DynamicToolset 在 `next()` 内部读 deps
- **node 流转固定**：UserPromptNode(一次) → ModelRequestNode → CallToolsNode → 循环或 End
- **history_processors 返回值约束**：不能为空，末尾必须是 ModelRequest

## Phase 1 用户故事

### US-001: 项目骨架

**目标**: 可运行的项目结构

- pyproject.toml（uv 管理，依赖：pydantic-ai-slim[openai], fastapi, uvicorn, pytest）
- 目录结构:
  ```
  src/
    agent/        # Agent loop 核心
    tools/        # 内置工具
    config/       # 配置管理
    server/       # FastAPI 接口
    storage/      # 文件系统持久化
  tests/
  ```
- 配置加载（环境变量 / .env）：API key、model 名称、base_url
- `uv run pytest` 能跑通

**验收**: 项目结构存在，`uv run pytest` 通过（即使只有空测试）

---

### US-002: Deps 依赖注入体系

**目标**: 定义 Agent 的依赖对象，所有业务状态通过 deps 传递

- `AgentDeps` dataclass：session_id, user_id, available_tools, config 等
- 创建 Agent 时指定 `deps_type=AgentDeps`
- Tool 函数通过 `RunContext[AgentDeps]` 访问依赖

**验收**: AgentDeps 可实例化，RunContext 类型标注正确

---

### US-003: Agent Loop 核心（手动 iter/next）

**目标**: 实现手动驱动的 agent loop

- 创建 Agent 实例（model, system_prompt, DynamicToolset）
- 用 `agent.iter()` + `run.next(node)` 实现循环
- 在每个 node 之间可插入自定义逻辑（日志、状态更新）
- 支持传入 message_history 恢复对话
- max_iterations 防止无限循环

**验收**: 给定 FunctionModel mock，agent loop 能完成多步 tool 调用并返回最终结果

---

### US-004: DynamicToolset 动态工具管理

**目标**: 每步动态决定可用工具集

- `get_tools(ctx: RunContext[AgentDeps])` 函数，读取 `ctx.deps.available_tools`
- `DynamicToolset(get_tools, per_run_step=True)`
- 支持在 iter 循环中通过修改 deps 动态增减工具
- Tool 函数通过 RunContext 获取 deps

**验收**: 在 iter 循环中修改 deps.available_tools 后，下一步 LLM 调用使用更新后的工具列表

---

### US-005: 内置工具集（最小集）

**目标**: 类 Claude Code 的基础工具

- `read_file(path: str) -> str` — 读取文件内容
- `write_file(path: str, content: str) -> str` — 写入文件
- `list_directory(path: str) -> str` — 列出目录内容
- `run_shell(command: str) -> str` — 执行 shell 命令（有超时限制）
- 所有工具函数签名：`async def xxx(ctx: RunContext[AgentDeps], ...) -> str`

**验收**: 每个工具能独立测试通过，参数校验正确

---

### US-006: SSE 流式输出

**目标**: 从 ModelRequestNode 拿流式输出，转成 SSE 事件

- 在 iter 循环中，遇到 ModelRequestNode 时用 `node.stream()` 获取流式响应
- SSE 事件类型：text（文本片段）、tool_call（工具调用）、tool_result（工具结果）、finish（结束）
- 事件格式：`data: {"type": "text", "content": "..."}\n\n`

**验收**: FunctionModel mock 下，SSE 事件流格式正确

---

### US-007: FastAPI 接口

**目标**: HTTP SSE endpoint

- `POST /chat/stream` — 接收用户消息，返回 SSE 流
  - 请求体：`{ "session_id": "...", "message": "..." }`
  - 响应：SSE 事件流
- `GET /health` — 健康检查

**验收**: 用 httpx 测试，能发起请求并收到 SSE 事件

---

### US-008: 消息持久化（文件系统）

**目标**: 会话消息用文件系统存储，重启不丢失

- 存储路径：`data/sessions/{session_id}/messages.json`
- 保存：每次 agent loop 结束后，用 `ModelMessagesTypeAdapter.dump_json()` 序列化
- 加载：请求进来时，用 `ModelMessagesTypeAdapter.validate_json()` 反序列化
- 传入 `agent.iter(message_history=loaded_messages)`

**验收**: agent loop 完成后消息被持久化，新请求能恢复历史并继续对话

---

### US-009: 错误处理 + LLM 重试

**目标**: LLM 调用失败时优雅处理

- Pydantic AI 自带 model 层重试（利用 ModelSettings 的 max_retries）
- tool 执行异常捕获，返回错误信息给 LLM 而不是崩溃
- iter 循环中的未知异常捕获，返回错误 SSE 事件

**验收**: 模拟 LLM 失败和 tool 异常，agent 不崩溃，返回错误信息

---

### US-010: 日志

**目标**: 结构化日志，方便调试

- 每次 LLM 调用记录：model、token 用量、耗时
- 每次 tool 调用记录：工具名、参数、结果、耗时
- 每个 session 记录：session_id、user_id、消息轮次

**验收**: agent loop 执行后，日志文件/输出中包含上述信息

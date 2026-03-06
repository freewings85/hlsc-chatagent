# ChatAgent 项目规则

## 代码规范

### 类型声明（强制，Java 级别严格）

所有 Python 代码必须像 Java 一样严格声明类型，无例外：

- **变量**：所有变量声明必须带类型注解
  ```python
  # 正确
  name: str = "hello"
  count: int = 0
  items: list[str] = []
  config: dict[str, Any] = {}
  result: AgentDeps | None = None

  # 错误
  name = "hello"
  count = 0
  ```

- **函数**：参数和返回值必须带类型注解
  ```python
  # 正确
  async def get_weather(ctx: RunContext[AgentDeps], city: str) -> str:

  # 错误
  async def get_weather(ctx, city):
  ```

- **类**：所有字段必须带类型注解
  ```python
  # 正确
  @dataclass
  class AgentDeps:
      session_id: str = "default"
      tool_map: dict[str, ToolFunc] = field(default_factory=dict)

  # 错误
  class AgentDeps:
      def __init__(self):
          self.session_id = "default"
  ```

- **类型别名**：复杂类型用 TypeAlias 定义
  ```python
  ToolFunc = Callable[..., str]
  ```

- **使用 mypy 检查**：`uv run mypy src/` 必须通过

### 其他规范

- 使用中文注释和文档
- 使用 `uv` 进行环境隔离
- 外部数据边界使用 Pydantic 做运行时校验
- docstring 用于 tool 函数的 description（Pydantic AI 会自动提取）

## 技术栈

- Python 3.12 + uv
- Pydantic AI（Agent + iter/next + deps + DynamicToolset）
- FastAPI + SSE
- pytest + FunctionModel mock

## 项目结构

```
src/
  agent/        # Agent loop 核心
  tools/        # 内置工具
  config/       # 配置管理
  server/       # FastAPI 接口
  storage/      # 文件系统持久化
tests/
```

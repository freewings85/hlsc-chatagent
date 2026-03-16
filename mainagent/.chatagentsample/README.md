# .chatagent 目录说明

本目录（`.chatagentsample/`）是 `.chatagent/` 的示例模板。

`.chatagent/` 被 `.gitignore` 忽略（因为包含运行时数据），所以用 `.chatagentsample/` 提交示例文件到仓库。

## 使用方式

首次开发时，将本目录内容复制到 `.chatagent/`：

```bash
cp -r .chatagentsample/* .chatagent/
```

## 目录结构

```
.chatagent/
  mcp.json              # MCP 服务器配置（可选）
  skills/               # 自定义 Skill 目录（可选）
    my_skill/
      SKILL.md          # Skill 定义
      scripts/          # 可执行脚本（可选）
      reference.md      # 参考文档（可选）
```

## MCP 配置

`mcp.json` 定义外部 MCP 服务器连接，格式：

```json
{
  "mcpServers": {
    "server-name": {
      "url": "http://localhost:8199/mcp",
      "headers": {"Authorization": "Bearer xxx"}
    }
  }
}
```

SDK 自动从 `{AGENT_FS_DIR}/mcp.json` 加载，无需在代码中配置。

## Skills

每个 Skill 是 `fstools/skills/` 下的一个子目录，包含 `SKILL.md` 文件（frontmatter + 指令）。

SDK 自动从 `{AGENT_FS_DIR}/fstools/skills/` 发现并加载所有 Skill，无需在代码中配置。

更多 Skill 编写示例参考 Anthropic 官方仓库：https://github.com/anthropics/skills

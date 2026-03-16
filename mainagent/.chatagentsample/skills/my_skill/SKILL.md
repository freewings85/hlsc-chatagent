---
name: my_skill
description: 示例 Skill，展示如何编写自定义 Skill。替换为你的 Skill 描述。
when_to_use: "Use when ... Triggers on: my skill, ..."
---

# My Skill

这是一个示例 Skill 模板。将本目录复制到 `.chatagent/fstools/skills/` 下即可生效。

## 使用说明

在这里编写 Skill 被调用时注入给 LLM 的指令。

## 目录结构

一个完整的 Skill 可以包含以下内容：

```
my_skill/
  SKILL.md              # Skill 定义（必须）— frontmatter + 指令
  scripts/              # 可执行脚本（可选）— Agent 可调用的 Python/Shell 脚本
    do_something.py
  reference.md          # 参考文档（可选）— 会被加载到 LLM 上下文
  assets/               # 静态资源（可选）— 模板、配置文件等
```

## 参考

更多 Skill 编写示例请参考 Anthropic 官方 Skills 仓库：
https://github.com/anthropics/skills

推荐参考 `pdf` skill（包含 scripts/ 和 reference 文件的完整示例）：
https://github.com/anthropics/skills/tree/main/skills/pdf

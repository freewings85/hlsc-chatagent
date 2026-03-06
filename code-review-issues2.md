# Code Review Issues — Codex Adversarial Rounds 2 & 3

## Round 2 Issues (4 items)

### R2-1: [High] save() 删后写非原子
- 状态: **Acknowledged** — BackendProtocol 不支持原子覆写，已文档化限制
- 生产环境需要后端 overwrite/rename 支持

### R2-2: [High] append() 同样删后写非原子
- 状态: **Acknowledged** — 同上

### R2-3: [Medium] _locks 无清理，长期内存增长
- 状态: **Acknowledged** — 实际场景 session 数有限，暂不修复

### R2-4: [Medium] 日志打印原始行内容可能泄露敏感信息
- 状态: **Fixed** — 改为只打印行长度

## Round 3 Issues (6 items)

### R3-1: [High] delete("/") 可删除根目录
- 状态: **Fixed** — 添加根目录保护检查 + 测试

### R3-2: [High] 文件操作无大小限制
- 状态: **Acknowledged** — 生产环境需要 size cap

### R3-3: [High] API 无鉴权
- 状态: **Known** — server/app.py 是 stub，生产环境需要认证层

### R3-4: [High] 无界队列和流式超时
- 状态: **Acknowledged** — 生产 DoS 防护需要有界队列 + 流超时

### R3-5: [Medium] Full compact 是 TODO
- 状态: **Known** — 按设计分阶段实现

### R3-6: [Medium] Mock 过于宽松
- 状态: **Acknowledged** — 单元测试 mock 的固有权衡

## Summary

3 轮 Codex 对抗审查共发现 18 个问题：
- **已修复**: 7 个（R1 的 Issue 2/3/4/8 + R2-4 + R3-1 + EventEmitter lock）
- **已知/设计限制**: 6 个（stub 模块、TODO 功能、Backend API 限制）
- **生产加固**: 5 个（认证、大小限制、超时、原子写入、锁清理）

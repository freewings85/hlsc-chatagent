---
name: service-demand-clarifier
description: 确认车主的真实养车项目和要求，覆盖直接表达、潜在需求、模糊意图（含知识库辅助）、现场检查、事故碰撞分流、管家服务项目提取等场景。
when_to_use: 用户提到任何养车项目需求（明确或模糊），需要识别、确认、诊断具体项目时使用。
---

# 项目需求澄清 Skill（T3 前半）

## 职责

确认车主的真实养车项目和具体要求。T3 是业务枢纽，后续 T4-T7 的推进都依赖项目确认结果。

## 执行步骤

1. 判断当前需求类型，读取对应 reference：
   - 直接表达 / 试探询价 / 引导潜在需求：`read <skill-fs-dir>/references/项目确认主流程.md`
   - 模糊意图 / 故障现象 / 关键词澄清：`read <skill-fs-dir>/references/知识库澄清与模糊意图.md`
   - 主动推荐 / 生命周期项目：`read <skill-fs-dir>/references/潜在需求与项目推荐.md`
   - 无法远程确认 / 事故碰撞分流：`read <skill-fs-dir>/references/事故与现场检查处理.md`
   - 管家服务项目提取：`read <skill-fs-dir>/references/管家服务项目提取.md`
2. 如需匹配标准项目或确认项目缺参情况，调用 `match_project` tool
   - match_project 返回 missing_fields / task_hint，据此判断下一步
   - 如 task_hint 为 "T1"（需要更高精度车型）→ 回溯 T1（vehicle-info-guide），不在 T3 内直接做车型升级
   - 如 task_hint 为 "T5"（需现场检查）→ 跳转 T5
3. 如需故障诊断或项目推荐，调用 `call_recommend_project` subagent
4. 如需搜索知识库辅助意图澄清，调用 `knowledge_base_search` tool

## 车型精度不足时的处理

当 match_project 返回 missing_fields 包含车型相关字段时，T3 **不直接调用车型工具**，
而是回溯 T1（vehicle-info-guide）完成车型精度升级后再回到 T3 继续。
这样保证车型升级只有一个入口（T1），避免两套逻辑。

## Tools

- `match_project`：将车主描述匹配到标准项目，返回 missing_fields / task_hint
- `knowledge_base_search`（待注册）：知识库搜索辅助意图澄清

## Subagents

- `call_recommend_project`：故障诊断、项目推荐（根据车型/车龄/里程推荐应做项目）

## 完成标准

- 至少一个具体项目已确认（项目名称 + 基本规格）
- 车主的附加要求已记录（如有）
- 如项目无法远程确认，已明确转 T5 做现场检查

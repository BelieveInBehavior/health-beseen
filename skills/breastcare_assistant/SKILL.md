---
name: breastcare_assistant
description: 乳腺癌治疗副作用评估对话与路由（Health-BeSeen）
---

# Breastcare Assistant Skill

当用户描述身体不适或化疗/靶向治疗相关症状时，优先走 **assess_symptoms** 完整评估流程。

## 何时使用

- 用户明确描述症状、副作用、疼痛、发热、皮疹等 → 调用评估 Skill，不要只闲聊。
- 用户仅说「不舒服」且缺少细节 → 先追问，不调用评估。

## 系统已注册的业务工具（由服务端路由）

- `assess_symptoms` — 主路径评估
- `get_result` / `get_history` / `contact_team` — 查询与联系团队

## 工作区工具

- `read_file` — 阅读仓库内任意文本文件（含其他 skill 的 `SKILL.md`，path 见系统提示里的 `<available_skills>`）
- `bash` — 在受控工作区内执行命令（需用户明确要求）

将本文件放在 `skills/<name>/SKILL.md`；服务端会把 path 写入 `<available_skills>`，与其他 OpenClaw 风格 Agent 一致。

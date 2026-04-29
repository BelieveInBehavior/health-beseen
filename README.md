# Health-BeSeen MVP

基于 FastAPI + React 的乳腺癌副作用评估原型，包含：
- 感知-决策-执行-学习闭环（规则优先，未命中时走规划器）
- MongoDB 持久化（assessments / event_logs / collaboration_requests）
- 文件系统 Memory（单次记录 + 聚合统计）
- 前端输入、结果、历史页面与事件上报

## 项目结构

```text
health-beseen/
├── client/
│   ├── package.json
│   ├── index.html
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts
│       ├── components/
│       │   ├── RiskBadge.tsx
│       │   └── EventTracker.ts
│       └── pages/
│           └── ChatPage.tsx
├── server/
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── routes/
│   │   ├── assessment.py
│   │   └── collaboration.py
│   ├── engine/
│   │   ├── agent.py
│   │   ├── perception.py
│   │   ├── rules.py
│   │   ├── planner.py
│   │   └── executor.py
│   ├── memory/
│   │   ├── manager.py
│   │   └── store/
│   └── events/
│       └── tracker.py
└── .gitignore
```

## 后端运行

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

默认地址：`http://localhost:8000`

### LLM Provider 配置（OpenAI / Azure / OpenRouter）

在项目根目录创建 `.env`，示例：

```bash
# 通用
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-xxx
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0.2
LLM_TOP_P=1.0
# 可选，默认 https://api.openai.com/v1
LLM_BASE_URL=https://api.openai.com/v1
```

OpenRouter 示例：

```bash
LLM_PROVIDER=openrouter
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-or-xxx
LLM_BASE_URL=https://openrouter.ai/api/v1
```

Azure OpenAI 示例：

```bash
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://admin-mbuirchl-eastus2.cognitiveservices.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-5-chat
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# 同样可配置采样参数
LLM_MAX_TOKENS=16384
LLM_TEMPERATURE=1.0
LLM_TOP_P=1.0
```

说明：
- 当 provider 配置缺失或调用失败时，系统会自动回退到本地 heuristic 规划器
- `LLM_PROVIDER` 支持：`openai` / `openrouter` / `azure`

## 前端运行

```bash
cd client
npm install
npm run dev
```

默认地址：`http://localhost:5173`

## API 概览

- `POST /api/assess` 提交副作用评估
- `GET /api/result/{id}` 获取单条结果
- `GET /api/history?session_id=...` 获取历史记录
- `POST /api/contact-team` 创建协同请求
- `POST /api/events` 上报事件

## Agent Tool-Use 设计

当前系统的交互模式是"用户输入 → 手动点按钮 → 调用固定 API"。下一步演进方向是引入 **LLM Tool-Use 路由层**，让模型根据用户自然语言自主决策调用哪个能力。

### 设计原则

将 API 能力分为两类：

| 类型 | 定义 | 特点 |
|------|------|------|
| **Skill** | 多步复合流程，串联多个原子操作 | 一次决策完成主路径 |
| **Tool** | 单步原子操作，独立可调用 | 支持回看、查询等独立场景 |

### Tool 定义

以下 4 个 Tool 供 LLM function calling 选择：

#### 1. `submit_assessment` — 提交症状评估

```json
{
  "name": "submit_assessment",
  "description": "用户描述了副作用或身体不适症状，需要进行风险评估。",
  "parameters": {
    "type": "object",
    "properties": {
      "user_input": {
        "type": "string",
        "description": "用户描述的症状文本"
      },
      "session_id": {
        "type": "string",
        "description": "当前会话 ID"
      }
    },
    "required": ["user_input", "session_id"]
  }
}
```

对应 API: `POST /api/assess`

#### 2. `get_result` — 查询已有评估结果

```json
{
  "name": "get_result",
  "description": "用户想查看某次已完成的评估结果详情。",
  "parameters": {
    "type": "object",
    "properties": {
      "assessment_id": {
        "type": "string",
        "description": "评估记录 ID"
      }
    },
    "required": ["assessment_id"]
  }
}
```

对应 API: `GET /api/result/{id}`

#### 3. `get_history` — 查询评估历史

```json
{
  "name": "get_history",
  "description": "用户想查看过往的评估记录列表和趋势。",
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "会话 ID，用于筛选该用户的历史"
      }
    },
    "required": ["session_id"]
  }
}
```

对应 API: `GET /api/history?session_id=...`

#### 4. `contact_team` — 联系医疗团队

```json
{
  "name": "contact_team",
  "description": "用户明确表达希望联系医疗团队或医生。",
  "parameters": {
    "type": "object",
    "properties": {
      "assessment_id": {
        "type": "string",
        "description": "关联的评估 ID（可选）"
      },
      "session_id": {
        "type": "string",
        "description": "会话 ID"
      },
      "reason": {
        "type": "string",
        "description": "联系原因"
      }
    },
    "required": ["session_id"]
  }
}
```

对应 API: `POST /api/contact-team`

### Skill 定义

#### `assess_symptoms` — 症状评估（复合流程）

这是主路径 Skill，串联多个 Tool 完成完整评估流程：

```
用户描述症状
  → submit_assessment（调用 Orchestrator Agent）
  → 自动获取结果（内部 get_result）
  → 组装展示（风险等级 + 建议 + 证据 + 审计信息）
```

Skill 内部执行流与现有 Orchestrator Agent 一致：

```
INIT → PERCEIVING → DECIDING → (LLM_AUGMENTING?) → EXECUTING → COMPLETE
```

**Skill vs 单独调 Tool 的区别**：Skill 是一次 LLM 决策触发完整流程，不需要模型再决策"要不要获取结果"。单独的 `get_result` Tool 用于回看场景。

### 路由决策逻辑

LLM 根据用户输入选择调用的 Tool/Skill，或直接文本回复：

```
用户输入
  │
  ├─ 描述了症状/身体不适 ──→ Skill: assess_symptoms
  │   例: "化疗后一直胸闷"
  │   例: "最近有点恶心，吃不下饭"
  │
  ├─ 想看之前的结果 ──→ Tool: get_result
  │   例: "刚才那个评估结果再看一下"
  │   例: "上次高风险的建议是什么"
  │
  ├─ 想看历史记录 ──→ Tool: get_history
  │   例: "我之前的评估记录"
  │   例: "看看历史趋势"
  │
  ├─ 想联系医生 ──→ Tool: contact_team
  │   例: "我想联系医疗团队"
  │   例: "帮我约一下医生"
  │
  └─ 闲聊/追问/信息不足 ──→ 直接文本回复（无 Tool）
      例: "你好"
      例: "不太舒服"（模型可追问: "具体哪里不舒服？"）
```

### 对话示例

**示例 1 — 主路径（Skill）**
```
用户: 化疗后呼吸困难，还有点胸闷
模型: [调用 assess_symptoms skill]
     → submit_assessment(user_input="化疗后呼吸困难，还有点胸闷")
     → 自动获取并展示结果
输出: 风险等级 HIGH，建议立即就医...
```

**示例 2 — 信息不足，先追问再评估**
```
用户: 不太舒服
模型: [无 tool] 请问具体是哪里不舒服？比如有没有发热、恶心、胸闷等症状？
用户: 有点低烧，大概37.8，已经两天了
模型: [调用 assess_symptoms skill]
输出: 风险等级 MID，建议联系团队评估...
```

**示例 3 — 回看旧结果（独立 Tool）**
```
用户: 刚才那个评估结果再给我看看
模型: [调用 get_result tool, assessment_id 从上下文获取]
输出: 展示缓存的评估结果（不重新评估）
```

**示例 4 — 查历史 + 查详情（Tool 组合）**
```
用户: 我上周的评估是什么级别
模型: [调用 get_history tool]
     → 找到匹配记录
     → [调用 get_result tool] 获取详情
输出: 上周三的评估为 LOW，建议是...
```

### 计划实现路径

```
server/engine/
├── router.py          ← 新增: Tool-Use 路由层
│   ├── TOOLS schema 定义（OpenAI function calling 格式）
│   ├── route(user_input, context) → tool_call | text_reply
│   └── execute_tool(tool_call) → result
├── agent.py           ← 现有: Orchestrator Agent（被 skill 内部调用）
├── rules.py           ← 现有: 规则引擎
├── planner.py         ← 现有: LLM Augment
└── ...
```

路由层位于 Agent 之上，作为最外层的意图识别与分发：

```
用户输入 → Router (LLM tool-use) → Tool/Skill 选择 → 执行 → 结果
                                        │
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                    assess_symptoms  get_result  get_history ...
                         │
                    Orchestrator Agent
                    (现有状态机)
```

---

## 快速验证

1. 输入 `化疗后发烧39度`，预期返回 `high` 风险
2. 输入 `有点恶心`，预期返回 `low` 风险
3. 查看 `history` 页面，确认记录可见
4. 检查 `server/memory/store/` 下是否生成评估 JSON 与 `_stats.json`

前端页面分两步：
- 主页输入副作用描述
- 进入聊天页面（`http://localhost:5173/`）后在消息流中展示助手文本回复（包含风险/建议/依据），并在你最近一次“发送/快捷选择”后短暂停顿的窗口内自动开始正式评估，随后进入“评估结果”页面。

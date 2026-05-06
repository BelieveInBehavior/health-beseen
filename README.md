# Health-BeSeen MVP

基于 FastAPI + React 的**可配置临床域**症状评估原型（助手身份由环境变量统一注入），包含：
- 感知-决策-执行-学习闭环（规则优先，未命中时走规划器）
- MongoDB 持久化（assessments / event_logs / collaboration_requests）
- 文件系统 Memory（单次记录 + 聚合统计）
- 前端输入、结果、历史页面与事件上报

**临床域**：路由（`router.py`）、Agent Loop（`agent_loop.py`）、规划器（`planner.py`）共用 `ASSISTANT_SYSTEM_ROLE`（默认「肿瘤治疗副作用评估助手」）。切换病种（如宫颈癌 / HPV / 宫颈病变）时设环境变量即可；**症状匹配逻辑**仍在 `server/engine/rules.py`，建议同步维护关键词与 `RULE_VERSION`，必要时重建规则嵌入缓存。

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
│       ├── userToken.ts
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
│   │   ├── chat.py        ← POST /api/chat（SSE，含工作区工具）
│   │   └── collaboration.py
│   ├── engine/
│   │   ├── agent.py
│   │   ├── assess_tool_args.py  ← LLM assess_symptoms 参数规范化 + 拼成 user_input
│   │   ├── perception.py
│   │   ├── rules.py
│   │   ├── planner.py
│   │   ├── rule_embedder.py
│   │   ├── user_memory.py
│   │   ├── rag_store.py
│   │   ├── summarizer.py
│   │   ├── router.py      ← LLM tool-use 路由（SKILL 经 read_file + skills_prompt 注入）
│   │   ├── skills_prompt.py
│   │   ├── skills_index.py   ← actone 式 load skills index（一层目录 + 平铺 .md）
│   │   ├── workspace_tools.py
│   │   └── executor.py
│   ├── memory/
│   │   ├── manager.py
│   │   └── store/
│   └── events/
│       └── tracker.py
├── skills/                ← Agent SKILL.md（注入 `<available_skills>`，经 read_file 读取）
│   └── breastcare_assistant/SKILL.md
└── .gitignore
```

## 后端运行

```bash
cd server
# 建议使用 Python 3.12 或 3.13（3.14 上 pydantic-core 可能无法预编译安装）
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

默认地址：`http://localhost:8000`

### VSCode Debug 后端

已提供可直接使用的 VSCode 配置：

- `.vscode/launch.json`：`Backend: Uvicorn (Debug)`
- `.vscode/tasks.json`：启动前自动执行 `docker compose stop server`，避免本地 Debug 与容器端口冲突

调试步骤：

1. 先确保基础依赖在运行（建议至少启动 MongoDB / Redis）：
   ```bash
   docker compose up -d mongodb redis
   ```
2. 确认 `server/.venv` 已安装依赖：
   ```bash
   cd server
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. 在 VSCode Run and Debug 里选择 `Backend: Uvicorn (Debug)`，按 `F5` 启动。

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

# 可选：助手对外身份（路由 / Agent / Planner 共用）
# ASSISTANT_SYSTEM_ROLE=宫颈癌及HPV相关随诊与症状评估助手
```

OpenRouter 示例：

```bash
LLM_PROVIDER=openrouter
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-or-xxx
LLM_BASE_URL=https://openrouter.ai/api/v1
```

### 工作区工具（actone-ai `backend` 对齐）与 Skill 索引

参考 `/Users/wangxinyu/Desktop/actone-ai/backend` 的 `agent_tools` / `agent_context`：

- **Skill 索引**：`server/engine/skills_index.py` 的 `load_skills_index_markdown()` 对应 actone `_load_skills_index`——在 `skills/` 下**只扫一层**（目录内 `SKILL.md` 或平铺 `*.md`），在 system 里生成 **Markdown 表格**（Skill / Description / File）+ 使用规则；完整内容用 **`read_file`** 读「File」列路径。`skills_prompt.py` 同时附带 `<available_skills>` XML。
- **不把「读 skill」做成单独 LLM 工具**，与 OpenClaw / actone 一致。

| 工具 | 作用 |
|------|------|
| `list_files` | 列出工作区内目录内容（path 相对根，空为根目录） |
| `glob_files` | 按 glob 枚举路径（如 `**/*.py`），不经过 shell |
| `grep` | 在工作区内用 **Python 正则**搜文件内容（非 shell，防注入）；可配 `GREP_MAX_*` |
| `read_file` | 读文本文件（含 SKILL.md；可选 offset/limit 按行） |
| `read_document` | 从 PDF / DOCX / XLSX 抽文本（依赖 pdfplumber、python-docx、openpyxl） |
| `write_file` | 写入/覆盖文本文件（`WORKSPACE_WRITE_ENABLED`） |
| `delete_file` | 删除单文件（`WORKSPACE_DELETE_PROTECTED` 保护部分路径） |
| `bash` | 在受控目录执行 `bash -lc`（可关）；搜代码优先 `grep`/`glob_files` |

环境变量示例：

```bash
# 可选：工作区根路径（默认项目根）
HEALTH_BESEEN_WORKSPACE=/path/to/health-beseen
# 相对工作区的 skill 目录，多个用 : 分隔（默认 skills）
SKILLS_DIR=skills
# 关闭 shell 工具（生产建议按需关闭）
ENABLE_BASH_TOOL=0
WORKSPACE_WRITE_ENABLED=0
WORKSPACE_DELETE_PROTECTED=.env,server/.env
WORKSPACE_BASH_TIMEOUT_SEC=60
WORKSPACE_BASH_MAX_OUTPUT_CHARS=80000
READ_FILE_MAX_BYTES=262144
READ_DOCUMENT_MAX_CHARS=24000
# grep / glob（Agent Loop 内与 bash 并列，不启 shell）
GREP_MAX_FILES=400
GREP_MAX_MATCHES=200
GLOB_MAX_RESULTS=500
# WORKSPACE_GREP_SKIP_DIRS=node_modules,.git,venv,.venv
```

自定义 Skill：在 `skills/<名称>/SKILL.md` 编写说明文档；启动对话时会被扫描进 `<available_skills>`，模型用 **`read_file`** 打开对应 path 即可（与 OpenClaw 用读文件工具打开 SKILL.md 的方式一致）。`SKILL.md` 不是单独的 `.yaml` 文件；若使用元数据，可在正文前用 `---` … `---` 包住 **YAML frontmatter**（与 OpenClaw `parseFrontmatterBlock` 语义一致），依赖 **PyYAML** 解析；若仅做服务端扩展解析可用 `server/engine/skill_snap.py`。

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

前端接口调用方式（当前默认）：
- 直接请求后端：`http://localhost:8000/api`
- 不依赖 Vite `/api` 代理
- 对话页：解析 SSE `message` 中可选的 `risk_level` / `assessment_id`；若本条助手文本为高风险（或与同轮 `risk` 事件衔接），在气泡下展示「立即线下就医 / 24h 联系团队」并调用 `POST /api/contact-team`（有 `assessment_id` 时）
- SSE 事件解析兼容 `event:xxx` / `event: xxx` 与 `data:xxx` / `data: xxx` 两种写法，并支持 `\n` 与 `\r\n` 换行分隔

## API 概览

- `POST /api/assess` 提交副作用评估
- `GET /api/result/{id}` 获取单条结果
- `GET /api/history?session_id=...` 获取历史记录
- `POST /api/contact-team` 创建协同请求
- `POST /api/events` 上报事件
- `POST /api/feedback` 上报用户反馈
- `POST /api/session/summarize` 触发会话摘要沉淀
- `POST /api/chat` 默认 **`use_agent_loop: true`**：多轮 Agent Loop，可连续调用 `read_file`、`bash`、`grep`、`glob_files` 等直至模型产出最终回复；设为 `false` 则退回单跳路由（每次最多一次工具调用）。

说明：`/api/assess` 与 `/api/chat` 请求需携带 `user_token`（前端通过 `localStorage` 持久化），用于跨 session 用户记忆与语义检索数据沉淀。

## Agent Tool-Use 设计

当前系统的交互模式是"用户输入 → 手动点按钮 → 调用固定 API"。下一步演进方向是引入 **LLM Tool-Use 路由层**，让模型根据用户自然语言自主决策调用哪个能力。

### 设计原则

将 API 能力分为两类：

| 类型 | 定义 | 特点 |
|------|------|------|
| **Skill** | 多步复合流程，串联多个原子操作 | 一次决策完成主路径 |
| **Tool** | 单步原子操作，独立可调用 | 支持回看、查询等独立场景 |

### Tool 定义

实现见 `server/engine/router.py`：**业务侧**以 `assess_symptoms`（主路径）、`get_result`、`get_history`、`contact_team` 为主；**仓库侧**为 `read_file` 与 `bash`。与 OpenClaw 一致，**不把读取 SKILL.md 做成单独工具**——可用 skill 的路径写在每条请求的 system 片段 `<available_skills>` 中，模型用 **`read_file`** 打开对应 path 即可。

下文仍以文档化的 schema 形式列出主要能力（名称与实现中 `function.name` 可能用 `assess_symptoms` 等统一命名）：

#### 1. `assess_symptoms` — 提交症状评估（结构化参数）

```json
{
  "name": "assess_symptoms",
  "description": "评估患者症状风险等级",
  "parameters": {
    "type": "object",
    "properties": {
      "symptoms": {
        "type": "array",
        "items": {"type": "string"},
        "description": "症状列表，如['胸闷', '发热']"
      },
      "location": {
        "type": "string",
        "description": "症状部位，如'胸口'、'腹部'"
      },
      "duration": {
        "type": "string",
        "description": "持续时间，如'两天'、'三小时'"
      }
    },
    "required": ["symptoms", "location", "duration"]
  }
}
```

对应执行：`assess_symptoms` 入参由 LLM 直接生成结构化 JSON，服务端将其拼装后调用评估链路（`run_assessment`）。

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
  → assess_symptoms({symptoms, location, duration})（调用 Orchestrator Agent）
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
     → assess_symptoms(symptoms=["呼吸困难","胸闷"], location="胸口", duration="未指定")
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

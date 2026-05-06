# 架构审查：Perceive 层是否必要

**结论：该分析基本正确。Perceive 层在当前场景下是冗余的中间层。**

---

## 1. 当前架构流程

```
user_input + history
    ↓
[PERCEIVING] perceive(user_input, prior, history)
    ↓ LLM 调用
PerceptionResult {symptoms, negated, confidence, needs_clarification}
    ↓
[DECIDING] rules.evaluate(user_input) → matched_rules?
    ├─ YES → use rule result (risk_level, advice, evidence)
    └─ NO → [LLM_AUGMENTING] augment(user_input, symptoms)
              ↓ LLM 调用
              {risk_level, advice, evidence}
    ↓
[EXECUTING] build final AssessmentResult
    ↓
persistence (MongoDB, Redis, RAG)
```

**两次 LLM 调用流程：**
1. `perceive()` - 提取结构化症状列表（JSON）
2. `augment()` - 基于症状列表给出建议

---

## 2. 分析的准确性验证

### ✅ 观点 1：模型本身就同时是感知层和决策层

**正确性：100%**

模型在生成回答的过程中自然就理解了症状，感知和决策在模型内部本来就是一体的。把这个过程拆成两个 LLM 调用，本质上是在用代码模拟模型内部已经在做的事情。

- 当前 `perceive()` 的职责：看对话历史，提取 JSON `{symptoms, negated, confidence}`
- 当前 `augment()` 的职责：看 `user_input` 和 `symptoms` 列表，输出 `{risk_level, advice, evidence}`
- 实际上 `augment()` 这样调用（planner.py:61）：
  ```python
  f"患者描述：{user_input}\n抽取症状：{', '.join(symptoms)}"
  ```
  即：将 perceive 的输出作为输入传给 augment，这正是问题所在。

**改进方案：**
```
user_input + history 
    ↓ 单次 LLM 调用（包含完整对话上下文）
{risk_level, advice, evidence, needs_clarification}
```

### ✅ 观点 2：规则引擎的核心价值是硬性风险拦截

**正确性：100%**

Rules.py 中的规则都是：
- **关键词驱动**（如 `keywords=["呼吸困难", "呼吸急促", ...]`）
- **硬性分级**（如"高热+出血+意识障碍" → high）
- **非概率性**（不能靠 LLM 随机性）

这部分**不依赖 perceive() 的结构化症状**。规则可以直接在 `user_input` 上匹配。

**多轮对话补充：** rules.py 目前只扫描 `user_input`，在多轮场景下会漏掉跨轮的症状状态（如用户第一轮说"发烧"，第二轮说"烧退了但胸闷"）。解决方案是让 rules.py 同时扫描最近 N 轮的 history，不需要感知层来做结构化，关键词匹配 history 就够了。

### ⚠️ 观点 3：Perceive 层有价值的三个场景

**场景 1：纯规则下游，完全不用 LLM**
- 当前：❌ 不符合（有 augment() 使用 LLM）

**场景 2：症状需持久化存储作为独立数据**
- 当前：⚠️ 部分符合
  - 代码确实保存 `perception_snapshots`（agent.py:70）
  - 但这些主要用于**增量更新** (prior)，而非病历归档
  - 真正的病历存储是 `SymptomTimeline`（agent.py:286），在 augment 之后
  - 结论：不是 perceive 存在的核心理由

**场景 3：系统延迟敏感，需分批处理**
- 当前：❌ 不符合
  - 流程完全串行：perceive → decide → augment
  - 没有流水线或并行处理

**结论：三个场景都不符合。**

---

## 3. Perceive 层当前的实际作用分析

### 作用 1：Needs Clarification 判断
```python
# agent.py:115-138
if perception.needs_clarification:
    return clarification_text  # 早期返回，避免继续处理
```
- **目的**：如果输入过于模糊（confidence < 阈值），提前澄清，避免浪费计算
- **问题**：augment() 也完全可以做这个判断（甚至更好，因为它有完整上下文）

### 作用 2：增量更新的 Prior 状态
```python
# agent.py:105
prior = await _load_perception_prior(db, session_id)
perception = await perceive(user_input, prior=prior, history=history)
```
- **目的**：多轮对话中，维持累积的症状状态（"不烧了"时，从 symptoms 移到 negated）
- **问题**：augment() 有完整对话历史，可以自己理解"不烧了"是什么意思

### 作用 3：为 Augment 准备输入
```python
# planner.py:61
f"患者描述：{user_input}\n抽取症状：{', '.join(symptoms)}"
```
- **目的**：限制 augment() 只看已知的症状标签（规范化输入）
- **问题**：
  - 增加了系统的严格度，可能限制 LLM 的灵活性
  - 如果 perceive 提取错了，augment 就基于错误的症状来评级
  - 是**两层 LLM 的级联**，而不是并行

**核心问题：为什么不让单个 LLM 在一个 prompt 里同时做"理解症状"和"评级"？**

---

## 4. 成本与收益分析

### 当前成本（保留 Perceive）
| 成本项 | 数值 |
|-------|------|
| **LLM 调用数** | 2 次（perceive + augment） |
| **延迟** | +1 个 perceive 往返（~200-500ms） |
| **API 成本** | 2x（两次调用） |
| **故障点** | perceive 失败 → fallback 降级 |

### 改进后的收益（删除 Perceive）
| 收益项 | 改进 |
|-------|------|
| **LLM 调用数** | 1 次（直接 augment with history） |
| **延迟** | -1 个往返 |
| **API 成本** | 50%（削减一半）|
| **故障点** | 减少一个降级环节 |
| **灵活性** | LLM 可以自由理解症状（不受词库限制） |

### 可能的风险
| 风险 | 缓解方案 |
|-------|---------|
| 失去"症状规范化"的约束 | augment() prompt 中可以指定"只返回已知症状标签" |
| 多轮对话中症状累积不清晰 | 对话历史本身就记录了所有消息，LLM 能理解累积 |
| rules.py 漏掉跨轮症状状态 | rules.py 改为扫描最近 N 轮 history，关键词匹配即可 |
| Needs clarification 判断不够早期 | 在 augment 的返回中判断，或在 router 层做 |

---

## 5. 建议的重构方案

### 新架构
```
用户输入
  ↓
rules.py 扫描 user_input + 最近 N 轮 history
  ├─ 高风险命中 → 直接返回紧急提示（不追问、不走 LLM）
  └─ 无命中 → augment(user_input, history)
                ↓ 单次 LLM 调用
                system prompt 控制追问 or 评估
                {risk_level, advice, evidence, needs_clarification?}
  ↓
[EXECUTING] build AssessmentResult
  ↓
persistence（symptoms 从 augment 返回中提取）
```

**关键原则：高风险关键词命中必须绕过追问逻辑。** 用户说"我喘不过气"，即使描述不完整，也应直接触发紧急提示，而不是被追问"持续多久了"。

### Augment System Prompt 核心逻辑

```
在给出评估之前，确认用户的描述包含以下三点：
1. 什么部位或系统（如胸口、腹部、全身）
2. 什么感觉（如疼痛、憋闷、发热、恶心）
3. 持续多久或频率如何

如果任何一点缺失，用一个简短的问题引导用户补充，不要评估。
三点都清晰后，才进入症状评估流程。
```

注意：不需要在 prompt 里描述"感知层"或"决策层"等架构概念，这些是代码层面的词汇。prompt 里只描述业务规则，模型自然完成理解和判断。

### 需要修改的文件

#### 1. `server/engine/agent.py`
```python
# 删除
- PERCEIVING 状态
- perceive() 调用
- _load_perception_prior() / _save_perception_snapshot()

# 修改
- DECIDING → 直接调用 augment()，传入完整 history
- 如果需要 symptoms 列表，让 augment 返回
```

#### 2. `server/engine/planner.py` (augment)
```python
# 修改 augment() 签名
async def augment(
    user_input: str,
    history: list[dict[str, str]] | None = None,
) -> dict:
    # 新 prompt 需要包含：
    # 1. 完整对话历史（不是只有 user_input）
    # 2. needs_clarification 的判断逻辑（三点是否齐全）
    # 3. 症状理解与风险评级合并
    
    # 返回：{risk_level, advice, evidence, needs_clarification, symptoms?}
```

#### 3. `server/engine/rules.py`
```python
# 修改 evaluate() 签名
def evaluate(
    user_input: str,
    history: list[dict[str, str]] | None = None,  # 新增
) -> RuleResult | None:
    # 扫描 user_input + 最近 N 轮 history
    # 保持关键词匹配逻辑不变
```

#### 4. `server/engine/perception.py`
```python
# 可选：保留 SYMPTOM_LEXICON + _keyword_fallback()
# 只作为 rules.py 的验证和 fallback
# 移除 perceive() 函数
```

### 影响范围
- ✅ 零 breaking changes 到 API（内部重构）
- ✅ 可以逐步迁移（先支持两种路径）
- ⚠️ 需要调整 RAG 存储逻辑（symptoms 来源从 perceive → augment）

---

## 6. 优先级与风险评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **改进幅度** | ⭐⭐⭐⭐ | 减少 50% LLM 调用，降低延迟 |
| **实现复杂度** | ⭐⭐ | 主要改动在 agent.py + planner.py + rules.py |
| **破坏性** | ⭐ | 内部重构，无 API breaking |
| **收益/成本比** | ⭐⭐⭐⭐⭐ | 高收益、低成本 |
| **建议优先级** | 🔴 高 | 可作为下一个优化任务 |

---

## 7. 相关代码位置

| 组件 | 文件 | 关键行 |
|------|------|--------|
| Perceive 层 | `server/engine/perception.py` | 95-174 |
| Agent 编排 | `server/engine/agent.py` | 100-187 |
| Augment 层 | `server/engine/planner.py` | 49-79 |
| 规则引擎 | `server/engine/rules.py` | 162-193 |
| 存储逻辑 | `server/engine/agent.py` | 50-79, 232-299 |

---

## 总结

✅ **分析准确**：当前 perceive 层是冗余的、增加成本的中间层。

**核心理由：**
1. 模型本身就同时是感知层和决策层，拆成两次调用是在用代码模拟模型内部已经在做的事
2. rules.py 用关键词匹配就够了，不需要 perceive 的结构化输入；多轮场景下改为扫描 history 即可
3. 没有"症状持久化独立使用"的真实需求
4. 没有分批处理的流水线设计

**推荐行动：**
- 删除 perceive() 函数
- rules.py 改为扫描 user_input + 最近 N 轮 history，高风险命中直接返回紧急提示
- 修改 augment() 接收完整对话历史，system prompt 控制追问逻辑（三点齐全才评估）
- 预期收益：-50% LLM 调用、-200-500ms 延迟、更好的灵活性

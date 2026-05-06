"""
Rule Engine — 高/中/低三层规则树, Priority 顺序匹配, 命中即停。

每条规则包含 id, level, keywords, advice, evidence, priority。
按 priority 降序遍历；同一 level 内按定义顺序。
命中 = 用户输入包含任一 keyword。最终取最高命中 level。
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from server.config import settings

RULE_VERSION = settings.RULE_VERSION


@dataclass
class Rule:
    id: str
    level: str          # "high" | "mid" | "low"
    priority: int       # higher = more urgent
    keywords: list[str]
    advice: str
    evidence: str
    matched_by: str = "keyword"


# ───────────────────── HIGH ─────────────────────
_HIGH_RULES = [
    Rule(
        id="R-HIGH-001", level="high", priority=100,
        keywords=["呼吸困难", "呼吸急促", "喘不过气", "无法呼吸"],
        advice="您描述的呼吸困难症状可能与免疫相关肺炎（irAE）有关，属于需要紧急处理的情况。建议立即停止当前治疗用药，24小时内前往医院进行胸部CT检查。",
        evidence="参考来源：NCCN指南 2024 · CTCAE v5.0 Grade 2+ 呼吸系统毒性",
    ),
    Rule(
        id="R-HIGH-003", level="high", priority=99,
        keywords=["胸闷", "胸痛", "心悸严重", "心跳异常"],
        advice="胸闷/胸痛可能提示心脏毒性或肺栓塞风险。建议24小时内就医，进行心电图和心肌标志物检查。",
        evidence="参考来源：NCCN指南 2024 · ESC肿瘤心脏病学指南",
    ),
    Rule(
        id="R-HIGH-005", level="high", priority=98,
        keywords=["高烧", "39度", "40度", "发烧39", "体温39", "高热"],
        advice="高热（≥39°C）可能提示严重感染或粒细胞缺乏症，属于肿瘤急症。建议立即就医进行血常规检查，必要时需要住院治疗。",
        evidence="参考来源：NCCN指南 2024 · 粒缺伴发热临床实践指南",
    ),
    Rule(
        id="R-HIGH-007", level="high", priority=97,
        keywords=["严重过敏", "过敏性休克", "喉咙肿", "喉头水肿", "全身荨麻疹"],
        advice="严重过敏反应需要立即处理！请拨打120或立即前往最近的急诊科。在等待期间保持平卧位，如有肾上腺素笔请立即使用。",
        evidence="参考来源：CTCAE v5.0 · 过敏反应 Grade 3-4 处理流程",
    ),
    Rule(
        id="R-HIGH-009", level="high", priority=96,
        keywords=["大量出血", "便血", "咯血", "吐血", "血尿"],
        advice="出血症状需要紧急评估！建议立即就医检查凝血功能和血常规。请避免剧烈活动，保持镇静。",
        evidence="参考来源：NCCN指南 2024 · 肿瘤相关出血管理",
    ),
    Rule(
        id="R-HIGH-011", level="high", priority=95,
        keywords=["意识模糊", "神志不清", "昏迷", "抽搐", "癫痫"],
        advice="意识障碍是紧急情况，请立即拨打120。在等待救护车期间，保持患者侧卧位，清除口腔异物。",
        evidence="参考来源：CTCAE v5.0 · 神经系统毒性 Grade 3-4",
    ),
]

# ───────────────────── MID ─────────────────────
_MID_RULES = [
    Rule(
        id="R-MID-002", level="mid", priority=60,
        keywords=["持续发热", "发烧超过", "低烧3天", "发热48", "反复发烧", "持续低烧"],
        advice="持续发热（>48小时）需要关注。建议联系您的医疗团队进行电话评估，同时记录每天体温变化。如体温超过38.5°C或出现寒战，请立即就医。",
        evidence="参考来源：NCCN指南 2024 · 免疫治疗相关发热鉴别诊断",
    ),
    Rule(
        id="R-MID-004", level="mid", priority=59,
        keywords=["注射部位", "肿痛", "红肿超过", "注射红肿", "注射疼痛"],
        advice="注射部位反应如果超过48小时未缓解或肿胀范围>5cm，建议联系医疗团队。可以先冷敷缓解不适，避免热敷和按摩该区域。",
        evidence="参考来源：CTCAE v5.0 · 注射部位反应 Grade 2",
    ),
    Rule(
        id="R-MID-006", level="mid", priority=58,
        keywords=["持续呕吐", "反复恶心", "无法进食", "严重恶心", "脱水"],
        advice="反复呕吐可能导致脱水和电解质紊乱。建议少量多次补液，如24小时内无法进食请联系团队评估是否需要静脉补液。",
        evidence="参考来源：NCCN止吐指南 2024 · CTCAE v5.0 消化系统毒性",
    ),
    Rule(
        id="R-MID-008", level="mid", priority=57,
        keywords=["皮疹面积大", "水泡", "破溃", "大面积皮疹", "皮肤脱皮"],
        advice="大面积皮疹或水泡/破溃需要密切观察。建议拍照记录并联系医疗团队，避免搔抓和阳光直射。",
        evidence="参考来源：CTCAE v5.0 · 皮肤毒性 Grade 2 · 免疫相关皮炎管理",
    ),
    Rule(
        id="R-MID-010", level="mid", priority=56,
        keywords=["腹泻严重", "腹泻超过", "水样便", "血便"],
        advice="严重腹泻可能是免疫相关肠炎的表现。建议记录排便次数和性状，联系团队评估是否需要激素治疗。",
        evidence="参考来源：NCCN指南 2024 · 免疫相关肠炎 Grade 2",
    ),
    Rule(
        id="R-MID-012", level="mid", priority=55,
        keywords=["发热", "发烧", "37.5", "38度", "低烧"],
        advice="低热需要持续监测。建议每4-6小时测量一次体温并记录，多饮水休息。如体温持续升高或超过48小时未退，请联系团队。",
        evidence="参考来源：CTCAE v5.0 · 发热 Grade 1-2",
    ),
]

# ───────────────────── LOW ─────────────────────
_LOW_RULES = [
    Rule(
        id="R-LOW-011", level="low", priority=30,
        keywords=["轻微恶心", "有点恶心", "偶尔恶心", "胃不舒服"],
        advice="轻微恶心是常见的治疗反应。建议少食多餐，避免油腻和刺激性食物，可以尝试生姜茶缓解症状。如果恶心加重请记录并在下次复诊时告知医生。",
        evidence="参考来源：NCCN止吐指南 2024 · 生活方式管理建议",
    ),
    Rule(
        id="R-LOW-013", level="low", priority=29,
        keywords=["疲劳", "乏力", "没力气", "体力下降", "容易累"],
        advice="疲劳是癌症治疗期间最常见的副作用。建议保持适度活动（如每天散步15-30分钟），保证充足睡眠，合理安排作息。持续加重请在复诊时反馈。",
        evidence="参考来源：NCCN癌因性疲劳指南 2024",
    ),
    Rule(
        id="R-LOW-015", level="low", priority=28,
        keywords=["头痛", "轻微头痛", "偶尔头痛"],
        advice="轻微头痛可以先观察。建议保持充足饮水和休息，必要时可服用对乙酰氨基酚。如头痛持续加重或伴随视力变化，请及时就医。",
        evidence="参考来源：CTCAE v5.0 · 神经系统毒性 Grade 1",
    ),
    Rule(
        id="R-LOW-017", level="low", priority=27,
        keywords=["食欲下降", "食欲差", "不想吃", "吃不下"],
        advice="食欲下降是常见反应。建议少量多餐，选择高蛋白、高热量易消化的食物。可以尝试在食欲较好的时段进食。持续体重下降请告知医生。",
        evidence="参考来源：NCCN营养支持指南 2024",
    ),
    Rule(
        id="R-LOW-019", level="low", priority=26,
        keywords=["皮肤干燥", "皮肤痒", "轻微红疹", "红疹", "有点痒", "皮疹"],
        advice="轻微皮肤反应较为常见。建议使用温和的保湿霜，避免热水洗浴和刺激性护肤品。如皮疹面积扩大或出现水泡，请及时联系团队。",
        evidence="参考来源：CTCAE v5.0 · 皮肤毒性 Grade 1",
    ),
    Rule(
        id="R-LOW-021", level="low", priority=25,
        keywords=["失眠", "睡眠差", "睡不好", "入睡困难"],
        advice="睡眠问题在治疗期间较为常见。建议保持规律作息，睡前避免使用电子设备，可以尝试放松训练。持续失眠影响生活质量请在复诊时反馈。",
        evidence="参考来源：NCCN生存者关怀指南 2024",
    ),
    Rule(
        id="R-LOW-023", level="low", priority=24,
        keywords=["手脚麻木", "指尖麻", "感觉异常"],
        advice="轻微的周围神经病变需要记录和观察。请注意手脚保暖，避免接触冷物，在下次复诊时详细反馈症状变化。",
        evidence="参考来源：CTCAE v5.0 · 周围神经病变 Grade 1",
    ),
]

ALL_RULES: list[Rule] = sorted(
    _HIGH_RULES + _MID_RULES + _LOW_RULES,
    key=lambda r: r.priority,
    reverse=True,
)


def evaluate(text: str) -> tuple[list[Rule], list[str], float]:
    """
    对输入文本执行规则匹配。

    Returns:
        matched: 命中的规则列表（按 priority 降序，命中最高级别即停）
        all_ids: 所有被评估的规则 ID
        confidence: 匹配置信度 (0-1)
    """
    matched: list[Rule] = []
    all_ids = [r.id for r in ALL_RULES]
    top_level: str | None = None

    for rule in ALL_RULES:
        hits = [kw for kw in rule.keywords if kw in text]
        if hits:
            if top_level is None:
                top_level = rule.level
            # 只收集与最高命中级别相同 level 的规则（命中即停策略）
            if rule.level == top_level:
                matched.append(rule)

    if not matched:
        return [], all_ids, 0.0

    # confidence = 命中规则的关键词命中率（只看命中的规则，不被未命中规则稀释）
    total_kws_in_matched = sum(len(r.keywords) for r in matched)
    hit_kws = sum(len([kw for kw in r.keywords if kw in text]) for r in matched)
    confidence = min(hit_kws / max(total_kws_in_matched, 1), 1.0)

    return matched, all_ids, confidence


async def evaluate_hybrid(
    text: str,
    rule_embeddings: list[dict],
) -> tuple[list[Rule], list[str], float]:
    """
    混合检索（关键词优先）：
    1) 先执行纯关键词 evaluate()，只要命中立即返回；
    2) 仅当关键词未命中时，才执行 embedding 语义检索并按 level-stop 返回。
    """
    from server.engine.rule_embedder import get_embedding

    all_ids = [r.id for r in ALL_RULES]

    # 先走纯关键词：只要命中就直接返回，不再计算 embedding
    kw_matched, _, kw_conf = evaluate(text)
    if kw_matched:
        return kw_matched, all_ids, kw_conf

    if not rule_embeddings:
        return [], all_ids, 0.0

    query_emb = await get_embedding(text)
    if not query_emb:
        return [], all_ids, 0.0

    sem_by_id: dict[str, float] = {
        row["rule_id"]: _cosine_similarity(query_emb, row.get("embedding") or [])
        for row in rule_embeddings
        if row.get("rule_id")
    }

    candidates: list[tuple[Rule, float]] = []
    for rule in ALL_RULES:
        sem_score = sem_by_id.get(rule.id, 0.0)

        # 关键词未命中时，仅依赖语义得分做候选
        if sem_score < settings.SEMANTIC_THRESHOLD:
            continue

        candidates.append((
            Rule(
                id=rule.id,
                level=rule.level,
                priority=rule.priority,
                keywords=rule.keywords,
                advice=rule.advice,
                evidence=rule.evidence,
                matched_by="semantic",
            ),
            sem_score,
        ))

    if not candidates:
        return [], all_ids, 0.0

    candidates.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
    top_level = candidates[0][0].level
    matched = [r for r, _ in candidates if r.level == top_level]
    confidence = max(s for r, s in candidates if r.level == top_level)
    return matched, all_ids, float(confidence)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


async def evaluate_semantic(
    text: str,
    rule_embeddings: list[dict],
) -> tuple[list[Rule], list[str], float]:
    """
    语义规则检索：输入文本 embedding 与规则 embedding 做 cosine 相似度。
    返回值与 evaluate() 对齐。
    """
    from server.engine.rule_embedder import get_embedding

    all_ids = [r.id for r in ALL_RULES]
    if not settings.SEMANTIC_RETRIEVAL_ENABLED or not rule_embeddings:
        return [], all_ids, 0.0

    query_emb = await get_embedding(text)
    if not query_emb:
        return [], all_ids, 0.0

    by_id = {r.id: r for r in ALL_RULES}
    candidates: list[tuple[Rule, float]] = []
    for row in rule_embeddings:
        rule_id = row.get("rule_id")
        emb = row.get("embedding") or []
        if rule_id not in by_id:
            continue
        score = _cosine_similarity(query_emb, emb)
        if score >= settings.SEMANTIC_THRESHOLD:
            src = by_id[rule_id]
            candidates.append((
                Rule(
                    id=src.id,
                    level=src.level,
                    priority=src.priority,
                    keywords=src.keywords,
                    advice=src.advice,
                    evidence=src.evidence,
                    matched_by="semantic",
                ),
                score,
            ))

    if not candidates:
        return [], all_ids, 0.0

    candidates.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
    top_level = candidates[0][0].level
    matched = [rule for rule, _ in candidates if rule.level == top_level]
    confidence = max(score for rule, score in candidates if rule.level == top_level)
    return matched, all_ids, float(confidence)

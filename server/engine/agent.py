"""
Assessment Orchestrator Agent
状态机: INIT → PERCEIVING → DECIDING → (LLM_AUGMENTING?) → EXECUTING → COMPLETE

感知 → 决策 → 执行 · Lifecycle 管理
"""

from __future__ import annotations

import enum
import logging
import uuid
from datetime import datetime, timezone

from server.config import settings
from server.engine.audit import build_audit_record, compute_content_hash
from server.engine.perception import extract_symptoms
from server.engine.planner import augment
from server.engine.rules import RULE_VERSION, Rule, evaluate
from server.models import AssessmentResult, RuleHit

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6


class State(str, enum.Enum):
    INIT = "INIT"
    PERCEIVING = "PERCEIVING"
    DECIDING = "DECIDING"
    LLM_AUGMENTING = "LLM_AUGMENTING"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"


async def run_assessment(session_id: str, user_input: str) -> tuple[AssessmentResult, dict]:
    """
    执行一次完整的评估流程。

    Returns:
        (AssessmentResult, audit_record_dict)
    """
    assessment_id = uuid.uuid4().hex[:12]
    state = State.INIT
    logger.info("[%s] state=%s", assessment_id, state)

    # ── PERCEIVING ──
    state = State.PERCEIVING
    logger.info("[%s] state=%s", assessment_id, state)
    symptoms = extract_symptoms(user_input)

    # ── DECIDING ──
    state = State.DECIDING
    logger.info("[%s] state=%s symptoms=%s", assessment_id, state, symptoms)
    matched_rules, all_rule_ids, confidence = evaluate(user_input)

    used_llm = False
    risk_level: str
    advice: str
    evidence: str

    if matched_rules:
        # 规则引擎命中 → 直接使用规则结果
        top_rule = matched_rules[0]
        risk_level = top_rule.level
        advice = top_rule.advice
        evidence = top_rule.evidence
    else:
        # 无规则命中 → LLM Augment
        state = State.LLM_AUGMENTING
        logger.info("[%s] state=%s no rules matched, trying LLM", assessment_id, state)
        llm_result = await augment(user_input, symptoms)
        risk_level = llm_result["risk_level"]
        advice = llm_result["advice"]
        evidence = llm_result["evidence"]
        used_llm = llm_result.get("used_llm", False)

    # ── EXECUTING ──
    state = State.EXECUTING
    logger.info("[%s] state=%s risk=%s", assessment_id, state, risk_level)

    matched_rule_hits = [
        RuleHit(
            id=r.id,
            level=r.level,
            keywords_matched=[kw for kw in r.keywords if kw in user_input],
            advice=r.advice,
            evidence=r.evidence,
        )
        for r in matched_rules
    ]

    content_hash = compute_content_hash(
        user_input, risk_level, advice, [r.id for r in matched_rules]
    )

    now = datetime.now(timezone.utc).isoformat()

    result = AssessmentResult(
        assessment_id=assessment_id,
        session_id=session_id,
        user_input=user_input,
        symptoms=symptoms,
        risk_level=risk_level,
        advice=advice,
        evidence=evidence,
        matched_rules=matched_rule_hits,
        all_evaluated_rules=all_rule_ids,
        rule_version=RULE_VERSION,
        model_version=settings.MODEL_VERSION if used_llm else "none",
        content_hash=content_hash,
        created_at=now,
    )

    audit = build_audit_record(assessment_id, matched_rules, content_hash, used_llm)

    # ── COMPLETE ──
    state = State.COMPLETE
    logger.info("[%s] state=%s", assessment_id, state)

    return result, audit

"""
Assessment Orchestrator Agent
状态机: INIT → PERCEIVING → DECIDING → (LLM_AUGMENTING?) → EXECUTING → COMPLETE

感知 → 决策 → 执行 · Lifecycle 管理
"""

from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from datetime import datetime, timezone

from server.config import settings
from server.db import get_db
from server.engine.audit import build_audit_record, compute_content_hash
from server.engine.perception import extract_symptoms
from server.engine.planner import augment
from server.engine.rag_store import save_expression_map, save_llm_augment_log, save_symptom_timeline, save_unmatched_query
from server.engine.rule_embedder import get_embedding, get_rule_embeddings_in_memory
from server.engine.rules import RULE_VERSION, evaluate, evaluate_hybrid, evaluate_semantic
from server.engine.user_memory import apply_memory_modifiers, load_user_memory, update_user_memory
from server.models import AssessmentResult, ExpressionRuleMap, LLMAugmentLog, RuleHit, SymptomTimeline, UnmatchedQuery

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6


class State(str, enum.Enum):
    INIT = "INIT"
    PERCEIVING = "PERCEIVING"
    DECIDING = "DECIDING"
    LLM_AUGMENTING = "LLM_AUGMENTING"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"


def _safe_bg(coro) -> None:
    async def _runner() -> None:
        try:
            await coro
        except Exception as e:
            logger.warning("background task failed: %s", e)
    asyncio.create_task(_runner())


async def run_assessment(
    session_id: str,
    user_input: str,
    user_token: str = "",
    parent_session_id: str = "admin",
    patient_id: str | None = None,
) -> tuple[AssessmentResult, dict]:
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
    db = get_db()
    memory = await load_user_memory(db, user_token, parent_session_id) if user_token else None

    # ── DECIDING ──
    state = State.DECIDING
    logger.info("[%s] state=%s symptoms=%s", assessment_id, state, symptoms)

    if settings.HYBRID_SEARCH_ENABLED:
        matched_rules, all_rule_ids, confidence = await evaluate_hybrid(
            user_input,
            get_rule_embeddings_in_memory(),
        )
        matched_by = matched_rules[0].matched_by if matched_rules else "none"
    else:
        # 旧级联路径（HYBRID_SEARCH_ENABLED=False 时保留）
        matched_rules, all_rule_ids, confidence = evaluate(user_input)
        matched_by = "keyword"
        if not matched_rules and settings.SEMANTIC_RETRIEVAL_ENABLED:
            sem_rules, all_rule_ids, sem_conf = await evaluate_semantic(
                user_input,
                get_rule_embeddings_in_memory(),
            )
            if sem_rules:
                matched_rules, confidence = sem_rules, sem_conf
                matched_by = "semantic"

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
        matched_by = "llm"

    risk_level = apply_memory_modifiers(risk_level, memory, symptoms)

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
            matched_by=r.matched_by,
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
        user_token=user_token,
        patient_id=patient_id,
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

    if settings.RAG_STORE_ENABLED and user_token:
        async def _persist_rag() -> None:
            emb = await get_embedding(user_input)
            expr = ExpressionRuleMap(
                doc_id=f"{assessment_id}-{matched_by}",
                session_id=session_id,
                user_token=user_token,
                parent_session_id=parent_session_id,
                patient_id=patient_id,
                assessment_id=assessment_id,
                user_input=user_input,
                user_input_embedding=emb,
                symptoms_extracted=symptoms,
                matched_rule_ids=[r.id for r in matched_rule_hits],
                matched_by=matched_by if matched_rules else "none",
                match_confidence=confidence,
                risk_level=risk_level,
                created_at=now,
            )
            await save_expression_map(db, expr)
            if matched_by == "llm":
                await save_llm_augment_log(
                    db,
                    LLMAugmentLog(
                        session_id=session_id,
                        user_token=user_token,
                        parent_session_id=parent_session_id,
                        patient_id=patient_id,
                        assessment_id=assessment_id,
                        user_input=user_input,
                        user_input_embedding=emb,
                        symptoms_extracted=symptoms,
                        llm_risk_level=risk_level,
                        llm_advice=advice,
                        llm_evidence=evidence,
                        created_at=now,
                    ),
                )
            if not matched_rules and matched_by == "llm":
                await save_unmatched_query(
                    db,
                    UnmatchedQuery(
                        session_id=session_id,
                        user_token=user_token,
                        parent_session_id=parent_session_id,
                        patient_id=patient_id,
                        user_input=user_input,
                        user_input_embedding=emb,
                        symptoms_extracted=symptoms,
                        llm_risk_level=risk_level,
                        llm_confidence=confidence,
                        created_at=now,
                    ),
                )
            await save_symptom_timeline(
                db,
                SymptomTimeline(
                    session_id=session_id,
                    user_token=user_token,
                    parent_session_id=parent_session_id,
                    patient_id=patient_id,
                    symptoms=symptoms,
                    risk_level=risk_level,
                    assessment_id=assessment_id,
                    created_at=now,
                ),
            )
        _safe_bg(_persist_rag())

    if user_token:
        _safe_bg(update_user_memory(db, session_id, user_token, result, symptoms, parent_session_id))

    # ── COMPLETE ──
    state = State.COMPLETE
    logger.info("[%s] state=%s", assessment_id, state)

    return result, audit

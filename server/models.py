from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssessmentRequest(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    user_input: str
    messages: list[dict[str, str]] = Field(default_factory=list)


class RuleHit(BaseModel):
    id: str
    level: str
    keywords_matched: list[str]
    advice: str
    evidence: str
    matched_by: str = "keyword"


class AssessmentResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    assessment_id: str
    session_id: str
    user_token: str
    patient_id: str | None = None
    user_input: str
    symptoms: list[str]
    risk_level: str
    advice: str
    evidence: str
    matched_rules: list[RuleHit]
    all_evaluated_rules: list[str]
    rule_version: str
    model_version: str
    content_hash: str
    created_at: str


class AuditRecord(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    assessment_id: str
    matched_rules: list[RuleHit]
    rule_snapshot: dict[str, Any]
    rule_version: str
    model_version: str
    content_hash: str
    created_at: str


class EventPayload(BaseModel):
    event_name: str
    session_id: str
    user_token: str = ""
    parent_session_id: str = "admin"
    patient_id: str | None = None
    assessment_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ContactRequest(BaseModel):
    assessment_id: str
    session_id: str
    user_token: str = ""
    patient_id: str | None = None
    reason: str = ""


class HistoryItem(BaseModel):
    assessment_id: str
    risk_level: str
    summary: str
    rule_version: str
    created_at: str


class HistoryResponse(BaseModel):
    trend: dict[str, int]
    items: list[HistoryItem]


class ChatRequest(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    # True：多轮 agent loop（read_file / bash / grep 等可连续调用）；False：单跳 route（兼容旧行为）
    use_agent_loop: bool = Field(default=True, description="是否使用多轮 Agent Loop")


class RouterDecision(BaseModel):
    type: str  # "tool_call" | "text"
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    text: str = ""


class SessionRequest(BaseModel):
    session_id: str
    user_token: str


class UserMemory(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    treatment_type: str | None = None
    treatment_drugs: list[str] = Field(default_factory=list)
    treatment_cycle: str | None = None
    known_allergies: list[str] = Field(default_factory=list)
    symptom_counts: dict[str, int] = Field(default_factory=dict)
    recent_risk_levels: list[dict[str, str]] = Field(default_factory=list)
    high_risk_count_30d: int = 0
    total_assessments: int = 0
    first_seen: str
    last_seen: str
    session_ids: list[str] = Field(default_factory=list)
    updated_at: str


class ExpressionRuleMap(BaseModel):
    doc_id: str
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    assessment_id: str
    user_input: str
    user_input_embedding: list[float] = Field(default_factory=list)
    symptoms_extracted: list[str] = Field(default_factory=list)
    matched_rule_ids: list[str] = Field(default_factory=list)
    matched_by: str
    match_confidence: float
    risk_level: str
    created_at: str


class UnmatchedQuery(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    user_input: str
    user_input_embedding: list[float] = Field(default_factory=list)
    symptoms_extracted: list[str] = Field(default_factory=list)
    llm_risk_level: str | None = None
    llm_confidence: float = 0.0
    resolved: bool = False
    created_at: str


class SessionSummary(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    summary: str
    summary_embedding: list[float] = Field(default_factory=list)
    primary_symptoms: list[str] = Field(default_factory=list)
    risk_levels_seen: list[str] = Field(default_factory=list)
    assessment_ids: list[str] = Field(default_factory=list)
    turn_count: int = 0
    created_at: str


class UserFeedback(BaseModel):
    assessment_id: str
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    feedback_type: str
    correction_text: str | None = None
    original_rule_id: str | None = None
    created_at: str


class SymptomTimeline(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    risk_level: str
    assessment_id: str
    created_at: str


class LLMAugmentLog(BaseModel):
    session_id: str
    user_token: str
    parent_session_id: str = "admin"
    patient_id: str | None = None
    assessment_id: str
    user_input: str
    user_input_embedding: list[float] = Field(default_factory=list)
    symptoms_extracted: list[str] = Field(default_factory=list)
    llm_risk_level: str
    llm_advice: str
    llm_evidence: str
    promoted_to_rule: bool = False
    created_at: str

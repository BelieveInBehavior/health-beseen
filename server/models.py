from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssessmentRequest(BaseModel):
    session_id: str
    user_input: str
    messages: list[dict[str, str]] = Field(default_factory=list)


class RuleHit(BaseModel):
    id: str
    level: str
    keywords_matched: list[str]
    advice: str
    evidence: str


class AssessmentResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    assessment_id: str
    session_id: str
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
    assessment_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ContactRequest(BaseModel):
    assessment_id: str
    session_id: str
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
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    # True：多轮 agent loop（read_file / bash / grep 等可连续调用）；False：单跳 route（兼容旧行为）
    use_agent_loop: bool = Field(default=True, description="是否使用多轮 Agent Loop")


class RouterDecision(BaseModel):
    type: str  # "tool_call" | "text"
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    text: str = ""

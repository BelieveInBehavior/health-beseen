"""
Audit Trail — 为每次评估生成审计记录。
包含: 命中规则快照, SHA-256 内容哈希, 版本号, 时间戳。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from server.config import settings
from server.engine.rules import Rule


def compute_content_hash(
    user_input: str,
    risk_level: str,
    advice: str,
    matched_rule_ids: list[str],
) -> str:
    """对评估结果内容计算 SHA-256 哈希，用于完整性校验。"""
    payload = json.dumps(
        {
            "user_input": user_input,
            "risk_level": risk_level,
            "advice": advice,
            "matched_rules": matched_rule_ids,
            "rule_version": settings.RULE_VERSION,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_audit_record(
    assessment_id: str,
    matched_rules: list[Rule],
    content_hash: str,
    used_llm: bool,
) -> dict:
    """构建审计记录文档。"""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "assessment_id": assessment_id,
        "matched_rules": [
            {"id": r.id, "level": r.level, "keywords": r.keywords, "advice": r.advice}
            for r in matched_rules
        ],
        "rule_snapshot": {
            "rule_version": settings.RULE_VERSION,
            "total_rules_evaluated": True,
        },
        "rule_version": settings.RULE_VERSION,
        "model_version": settings.MODEL_VERSION if used_llm else "none",
        "content_hash": content_hash,
        "created_at": now,
    }

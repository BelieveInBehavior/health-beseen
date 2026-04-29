"""
Response Assembler — 将评估结果通过 SSE 流式输出。
事件序列: risk → advice → evidence → rule_source → audit → complete
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from server.models import AssessmentResult


async def stream_result(result: AssessmentResult) -> AsyncGenerator[dict, None]:
    """生成 SSE 事件流。每个事件为 dict(event=..., data=...)，由 sse-starlette 格式化。"""

    # 1. risk
    yield _sse("risk", {
        "risk_level": result.risk_level,
        "assessment_id": result.assessment_id,
    })

    # 2. advice
    yield _sse("advice", {
        "advice": result.advice,
    })

    # 3. evidence
    yield _sse("evidence", {
        "evidence": result.evidence,
    })

    # 4. rule_source
    yield _sse("rule_source", {
        "matched_rules": [r.model_dump() for r in result.matched_rules],
        "all_evaluated_rules": result.all_evaluated_rules,
    })

    # 5. audit
    yield _sse("audit", {
        "rule_version": result.rule_version,
        "model_version": result.model_version,
        "content_hash": result.content_hash,
        "created_at": result.created_at,
        "assessment_id": result.assessment_id,
    })

    # 6. complete
    yield _sse("complete", {
        "assessment_id": result.assessment_id,
        "status": "done",
    })


def _sse(event: str, data: dict) -> dict:
    """返回 sse-starlette 期望的 dict 格式。"""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}

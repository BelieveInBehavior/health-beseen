"""
Assessment routes:
  POST /api/assess          — 提交评估 (SSE 流式返回)
  GET  /api/result/{id}     — 获取单条结果
  GET  /api/history         — 获取历史记录 + 趋势
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from server.cache import get_assessment_cache, set_assessment_cache
from server.db import get_db
from server.engine.agent import run_assessment
from server.engine.executor import stream_result
from server.memory.manager import save_assessment
from server.models import AssessmentRequest, HistoryItem, HistoryResponse

router = APIRouter(prefix="/api")


@router.post("/assess")
async def assess(req: AssessmentRequest):
    """提交评估 → Orchestrator → SSE stream."""
    result, audit = await run_assessment(
        req.session_id,
        req.user_input,
        user_token=req.user_token,
        parent_session_id=req.parent_session_id,
    )

    # Persist to MongoDB
    db = get_db()
    await db.assessments.insert_one(result.model_dump())
    await db.audit_records.insert_one(audit)

    # Cache in Redis L1
    await set_assessment_cache(result.assessment_id, result.model_dump())

    # File-system memory
    save_assessment(result)

    return EventSourceResponse(stream_result(result))


@router.get("/result/{assessment_id}")
async def get_result(assessment_id: str):
    """获取单条评估结果。优先 Redis 缓存。"""
    # Try L1 cache
    cached = await get_assessment_cache(assessment_id)
    if cached:
        return cached

    # Fallback to MongoDB
    db = get_db()
    doc = await db.assessments.find_one({"assessment_id": assessment_id}, {"_id": 0})
    if doc:
        await set_assessment_cache(assessment_id, doc)
        return doc
    return {"error": "not found"}


@router.get("/history", response_model=HistoryResponse)
async def get_history(session_id: str = Query(...)):
    """获取历史记录 + 趋势统计。"""
    db = get_db()
    cursor = db.assessments.find(
        {"session_id": session_id},
        {"_id": 0, "assessment_id": 1, "risk_level": 1, "user_input": 1,
         "rule_version": 1, "created_at": 1},
    ).sort("created_at", -1).limit(50)

    items: list[HistoryItem] = []
    trend = {"high": 0, "mid": 0, "low": 0}

    async for doc in cursor:
        level = doc["risk_level"]
        trend[level] = trend.get(level, 0) + 1
        items.append(HistoryItem(
            assessment_id=doc["assessment_id"],
            risk_level=level,
            summary=doc["user_input"][:40],
            rule_version=doc["rule_version"],
            created_at=doc["created_at"],
        ))

    return HistoryResponse(trend=trend, items=items)

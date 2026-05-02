from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from server.engine.rag_store import save_session_summary
from server.engine.rule_embedder import get_embedding
from server.models import SessionSummary


async def summarize_session(db: AsyncIOMotorDatabase, session_id: str, user_token: str) -> None:
    cursor = db.assessments.find(
        {"session_id": session_id, "user_token": user_token},
        {"_id": 0, "assessment_id": 1, "symptoms": 1, "risk_level": 1, "user_input": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20)
    rows = [row async for row in cursor]
    if not rows:
        return
    primary_symptoms: list[str] = []
    risk_levels: list[str] = []
    assessment_ids: list[str] = []
    for row in rows:
        for s in row.get("symptoms", []) or []:
            if s not in primary_symptoms:
                primary_symptoms.append(s)
        r = row.get("risk_level")
        if isinstance(r, str) and r not in risk_levels:
            risk_levels.append(r)
        aid = row.get("assessment_id")
        if isinstance(aid, str):
            assessment_ids.append(aid)
    latest = rows[0]
    summary = (
        f"本次会话共 {len(rows)} 次评估，最新风险等级为 {latest.get('risk_level', 'unknown')}，"
        f"主要症状包括：{'、'.join(primary_symptoms[:5]) or '未识别'}。"
    )
    emb = await get_embedding(summary)
    doc = SessionSummary(
        session_id=session_id,
        user_token=user_token,
        summary=summary,
        summary_embedding=emb,
        primary_symptoms=primary_symptoms[:10],
        risk_levels_seen=risk_levels,
        assessment_ids=assessment_ids,
        turn_count=len(rows),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await save_session_summary(db, doc)

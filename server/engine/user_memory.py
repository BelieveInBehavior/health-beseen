from __future__ import annotations

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from server.models import AssessmentResult, UserMemory


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def load_user_memory(
    db: AsyncIOMotorDatabase,
    user_token: str,
    parent_session_id: str = "admin",
) -> UserMemory | None:
    doc = await db.user_memories.find_one(
        {"user_token": user_token, "parent_session_id": parent_session_id},
        {"_id": 0},
    )
    if not doc:
        return None
    return UserMemory(**doc)


def _upgrade_level(level: str) -> str:
    if level == "low":
        return "mid"
    if level == "mid":
        return "high"
    return level


def apply_memory_modifiers(base_risk: str, memory: UserMemory | None, symptoms: list[str]) -> str:
    if memory is None:
        return base_risk
    adjusted = base_risk
    repeated = any(v >= 3 for v in memory.symptom_counts.values())
    if repeated:
        adjusted = _upgrade_level(adjusted)
    has_irAE_context = memory.treatment_type == "免疫治疗" and any(
        s in symptoms for s in ("呼吸困难", "胸闷", "皮肤反应")
    )
    if has_irAE_context:
        adjusted = _upgrade_level(adjusted)
    if base_risk == "mid" and memory.high_risk_count_30d >= 2:
        adjusted = "high"
    return adjusted


async def update_user_memory(
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_token: str,
    assessment: AssessmentResult,
    symptoms: list[str],
    parent_session_id: str = "admin",
) -> None:
    now = datetime.now(timezone.utc)
    existing = await load_user_memory(db, user_token, parent_session_id)
    if existing is None:
        doc = UserMemory(
            session_id=session_id,
            user_token=user_token,
            parent_session_id=parent_session_id,
            patient_id=assessment.patient_id,
            first_seen=now.isoformat(),
            last_seen=now.isoformat(),
            updated_at=now.isoformat(),
            session_ids=[session_id],
            symptom_counts={s: 1 for s in symptoms},
            recent_risk_levels=[{"risk_level": assessment.risk_level, "date": now.date().isoformat()}],
            high_risk_count_30d=1 if assessment.risk_level == "high" else 0,
            total_assessments=1,
        )
        await db.user_memories.insert_one(doc.model_dump())
        return

    counts = dict(existing.symptom_counts)
    for s in symptoms:
        counts[s] = counts.get(s, 0) + 1

    recent = list(existing.recent_risk_levels)
    recent.append({"risk_level": assessment.risk_level, "date": now.date().isoformat()})
    cutoff = now - timedelta(days=30)
    trimmed = []
    for row in recent[-200:]:
        try:
            d = datetime.fromisoformat(f"{row.get('date')}T00:00:00+00:00")
            if d >= cutoff:
                trimmed.append(row)
        except Exception:
            continue
    high_30d = sum(1 for row in trimmed if row.get("risk_level") == "high")

    await db.user_memories.update_one(
        {"user_token": user_token, "parent_session_id": parent_session_id},
        {
            "$set": {
                "session_id": session_id,
                "patient_id": assessment.patient_id,
                "symptom_counts": counts,
                "recent_risk_levels": trimmed,
                "high_risk_count_30d": high_30d,
                "last_seen": _now_iso(),
                "updated_at": _now_iso(),
            },
            "$inc": {"total_assessments": 1},
            "$addToSet": {"session_ids": session_id},
        },
    )

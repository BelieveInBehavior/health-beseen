from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from server.models import (
    ExpressionRuleMap,
    LLMAugmentLog,
    SessionSummary,
    SymptomTimeline,
    UnmatchedQuery,
    UserFeedback,
    UserMemory,
)


async def save_user_memory(db: AsyncIOMotorDatabase, doc: UserMemory) -> None:
    """乐观锁 upsert：按 (user_token, parent_session_id) 匹配，存在则更新，不存在则插入。"""
    await db.user_memories.update_one(
        {"user_token": doc.user_token, "parent_session_id": doc.parent_session_id},
        {"$set": doc.model_dump()},
        upsert=True,
    )


async def save_expression_map(db: AsyncIOMotorDatabase, doc: ExpressionRuleMap) -> None:
    await db.expression_rule_map.insert_one(doc.model_dump())


async def save_unmatched_query(db: AsyncIOMotorDatabase, doc: UnmatchedQuery) -> None:
    await db.unmatched_queries.insert_one(doc.model_dump())


async def save_llm_augment_log(db: AsyncIOMotorDatabase, doc: LLMAugmentLog) -> None:
    await db.llm_augment_log.insert_one(doc.model_dump())


async def save_user_feedback(db: AsyncIOMotorDatabase, doc: UserFeedback) -> None:
    await db.user_feedback.insert_one(doc.model_dump())


async def save_session_summary(db: AsyncIOMotorDatabase, doc: SessionSummary) -> None:
    await db.session_summaries.update_one(
        {"session_id": doc.session_id, "user_token": doc.user_token},
        {"$set": doc.model_dump()},
        upsert=True,
    )


async def save_symptom_timeline(db: AsyncIOMotorDatabase, doc: SymptomTimeline) -> None:
    await db.symptom_timeline.insert_one(doc.model_dump())

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from server.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _db = _client.get_default_database()
    # Create indexes
    await _db.assessments.create_index("session_id")
    await _db.assessments.create_index("created_at")
    await _db.event_logs.create_index("event_name")
    await _db.event_logs.create_index("created_at")
    await _db.audit_records.create_index("assessment_id", unique=True)
    await _db.contact_requests.create_index("assessment_id")
    await _db.expression_rule_map.create_index([("session_id", 1), ("created_at", -1)])
    await _db.expression_rule_map.create_index("user_token")
    await _db.unmatched_queries.create_index([("session_id", 1), ("created_at", -1)])
    await _db.user_feedback.create_index([("assessment_id", 1), ("created_at", -1)])
    await _db.session_summaries.create_index([("session_id", 1), ("user_token", 1)], unique=True)
    await _db.symptom_timeline.create_index([("user_token", 1), ("created_at", -1)])
    await _db.llm_augment_log.create_index([("session_id", 1), ("created_at", -1)])
    await _db.user_memories.create_index(
        [("user_token", 1), ("parent_session_id", 1)], unique=True
    )


async def close_mongo() -> None:
    global _client
    if _client:
        _client.close()


def get_db() -> AsyncIOMotorDatabase:
    assert _db is not None, "MongoDB not initialized — call init_mongo() first"
    return _db

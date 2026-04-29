"""
Event Tracker — 5 个核心事件写入 MongoDB event_logs 集合。

事件:
  1. assessment_started
  2. assessment_submitted
  3. result_viewed
  4. contact_team_clicked
  5. assessment_closed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from server.db import get_db

logger = logging.getLogger(__name__)

VALID_EVENTS = {
    "assessment_started",
    "assessment_submitted",
    "result_viewed",
    "contact_team_clicked",
    "assessment_closed",
}


async def track_event(
    event_name: str,
    session_id: str,
    assessment_id: str | None = None,
    payload: dict | None = None,
) -> str | None:
    """记录一个事件到 MongoDB。返回插入的文档 _id 字符串，或 None。"""
    if event_name not in VALID_EVENTS:
        logger.warning("Unknown event: %s", event_name)
        return None

    db = get_db()
    doc = {
        "event_name": event_name,
        "session_id": session_id,
        "assessment_id": assessment_id,
        "payload": payload or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.event_logs.insert_one(doc)
    logger.info("Tracked event %s for session %s", event_name, session_id)
    return str(result.inserted_id)

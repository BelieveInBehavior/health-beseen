"""
Event routes:
  POST /api/events — 接收前端埋点事件
"""

from __future__ import annotations

import asyncio
from fastapi import APIRouter

from server.db import get_db
from server.engine.summarizer import summarize_session
from server.events.tracker import track_event
from server.models import EventPayload

router = APIRouter(prefix="/api")


@router.post("/events")
async def post_event(ev: EventPayload):
    """接收并记录埋点事件。"""
    doc_id = await track_event(
        event_name=ev.event_name,
        session_id=ev.session_id,
        user_token=ev.user_token,
        patient_id=ev.patient_id,
        assessment_id=ev.assessment_id,
        payload=ev.payload,
    )
    if ev.event_name == "assessment_closed" and ev.user_token:
        asyncio.create_task(summarize_session(get_db(), ev.session_id, ev.user_token))
    return {"ok": True, "id": doc_id}

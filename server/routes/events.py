"""
Event routes:
  POST /api/events — 接收前端埋点事件
"""

from __future__ import annotations

from fastapi import APIRouter

from server.events.tracker import track_event
from server.models import EventPayload

router = APIRouter(prefix="/api")


@router.post("/events")
async def post_event(ev: EventPayload):
    """接收并记录埋点事件。"""
    doc_id = await track_event(
        event_name=ev.event_name,
        session_id=ev.session_id,
        assessment_id=ev.assessment_id,
        payload=ev.payload,
    )
    return {"ok": True, "id": doc_id}

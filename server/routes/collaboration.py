"""
Collaboration routes:
  POST /api/contact-team — 创建协同请求
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from server.db import get_db
from server.models import ContactRequest

router = APIRouter(prefix="/api")


@router.post("/contact-team")
async def contact_team(req: ContactRequest):
    """创建协同请求，写入 contact_requests 集合。"""
    db = get_db()
    doc = {
        "assessment_id": req.assessment_id,
        "session_id": req.session_id,
        "reason": req.reason,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.contact_requests.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending"}

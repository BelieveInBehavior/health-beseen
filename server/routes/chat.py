"""
Chat route — POST /api/chat

统一对话入口。LLM 路由器决策后，根据意图类型生成不同的 SSE 事件流：
  text       → intent + message + complete
  assessment → intent + risk + advice + evidence + rule_source + audit + complete
  history    → intent + history + complete
  result     → intent + result + complete
  contact    → intent + contact + complete
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from server.cache import get_assessment_cache, set_assessment_cache
from server.db import get_db
from server.engine.agent import run_assessment
from server.engine.executor import stream_result
from server.engine.router import route
from server.memory.manager import save_assessment
from server.models import ChatRequest, HistoryItem, HistoryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _handle_assessment(session_id: str, symptoms_text: str) -> AsyncGenerator[dict, None]:
    """执行评估并流式输出结果。"""
    yield _sse("intent", {"type": "assessment"})

    result, audit = await run_assessment(session_id, symptoms_text)

    # Persist
    db = get_db()
    await db.assessments.insert_one(result.model_dump())
    await db.audit_records.insert_one(audit)
    await set_assessment_cache(result.assessment_id, result.model_dump())
    save_assessment(result)

    # Stream existing SSE events
    async for event in stream_result(result):
        yield event


async def _handle_history(session_id: str) -> AsyncGenerator[dict, None]:
    """查询历史记录。"""
    yield _sse("intent", {"type": "history"})

    db = get_db()
    cursor = db.assessments.find(
        {"session_id": session_id},
        {"_id": 0, "assessment_id": 1, "risk_level": 1, "user_input": 1,
         "rule_version": 1, "created_at": 1},
    ).sort("created_at", -1).limit(50)

    items: list[dict] = []
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
        ).model_dump())

    history_data = HistoryResponse(trend=trend, items=items).model_dump()
    yield _sse("history", history_data)
    yield _sse("complete", {"status": "done"})


async def _handle_result(session_id: str, assessment_id: str) -> AsyncGenerator[dict, None]:
    """查询单条评估结果。"""
    yield _sse("intent", {"type": "result"})

    # "latest" 特殊值 → 取最新一条
    if assessment_id == "latest":
        db = get_db()
        doc = await db.assessments.find_one(
            {"session_id": session_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
    else:
        # 先查缓存
        cached = await get_assessment_cache(assessment_id)
        doc = cached
        if not doc:
            db = get_db()
            doc = await db.assessments.find_one(
                {"assessment_id": assessment_id}, {"_id": 0}
            )

    if doc:
        yield _sse("result", doc)
    else:
        yield _sse("result", {"error": "未找到评估记录"})

    yield _sse("complete", {"status": "done"})


async def _handle_contact(session_id: str, reason: str) -> AsyncGenerator[dict, None]:
    """创建协同请求。"""
    yield _sse("intent", {"type": "contact"})

    db = get_db()
    from datetime import datetime, timezone
    doc = {
        "session_id": session_id,
        "reason": reason or "用户请求联系医疗团队",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    inserted = await db.contact_requests.insert_one(doc)

    yield _sse("contact", {
        "id": str(inserted.inserted_id),
        "status": "pending",
        "message": "已为您提交医疗团队联系请求，团队会尽快与您取得联系。",
    })
    yield _sse("complete", {"status": "done"})


async def _handle_text(text: str) -> AsyncGenerator[dict, None]:
    """纯文本回复。"""
    yield _sse("intent", {"type": "text"})
    yield _sse("message", {"content": text})
    yield _sse("complete", {"status": "done"})


async def chat_stream(req: ChatRequest) -> AsyncGenerator[dict, None]:
    """根据路由决策生成 SSE 事件流。"""
    decision = await route(req.message, req.history, req.session_id)
    logger.info(
        "Router decision: type=%s tool=%s",
        decision.type, decision.tool_name,
    )

    if decision.type == "text":
        async for event in _handle_text(decision.text):
            yield event
        return

    # tool_call
    tool = decision.tool_name
    args = decision.tool_args

    if tool == "submit_assessment":
        symptoms_text = args.get("symptoms_text", req.message)
        async for event in _handle_assessment(req.session_id, symptoms_text):
            yield event

    elif tool == "get_history":
        async for event in _handle_history(req.session_id):
            yield event

    elif tool == "get_result":
        aid = args.get("assessment_id", "latest")
        async for event in _handle_result(req.session_id, aid):
            yield event

    elif tool == "contact_team":
        reason = args.get("reason", "")
        async for event in _handle_contact(req.session_id, reason):
            yield event

    else:
        # 未知 tool → 降级为文本
        async for event in _handle_text(decision.text or "抱歉，我没有理解您的意思。"):
            yield event


@router.post("/chat")
async def chat(req: ChatRequest):
    """统一对话入口 — SSE 流式响应。"""
    return EventSourceResponse(chat_stream(req))

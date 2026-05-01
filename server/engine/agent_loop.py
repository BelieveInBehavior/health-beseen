"""
多轮 Agent Loop — 与单跳 `route()` 使用同一套 TOOLS（含 actone 风格 list_files / read_file / read_document / write_file / delete_file / bash）。

Skills：由 `skills_prompt` 注入 actone 式索引表 + `<available_skills>`；用 **read_file** 读 File 列 path。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from server.cache import get_assessment_cache, set_assessment_cache
from server.config import settings
from server.db import get_db
from server.engine import router as router_mod
from server.engine.agent import run_assessment
from server.engine.executor import stream_result
from server.engine.skills_prompt import build_openclaw_skills_section
from server.engine.workspace_tools import (
    bash_tool,
    delete_file_tool,
    glob_files_tool,
    grep_tool,
    list_files_tool,
    read_document_tool,
    read_file_tool,
    write_file_tool,
)
from server.memory.manager import save_assessment
from server.models import HistoryItem, HistoryResponse

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _build_agent_loop_system_content() -> str:
    return (
        "你是乳腺癌治疗副作用评估助手，可通过工具完成用户请求。\n\n"
        + build_openclaw_skills_section()
        + "\n## 医疗路由备注\n"
        "- 用户症状描述模糊时先追问，勿直接 assess_symptoms。\n"
        "- 用中文回复。\n"
    )


async def _persist_assessment(result, audit) -> None:
    db = get_db()
    await db.assessments.insert_one(result.model_dump())
    await db.audit_records.insert_one(audit)
    await set_assessment_cache(result.assessment_id, result.model_dump())
    save_assessment(result)


async def _dispatch_tool(
    name: str,
    args: dict[str, Any],
    *,
    session_id: str,
    user_message: str,
) -> tuple[str, list[dict]]:
    """执行单步工具，返回 (OpenAI tool 消息 JSON 字符串, 需下发的 SSE 事件列表)。"""
    ev: list[dict] = []

    if name == "assess_symptoms":
        symptoms = str(args.get("symptoms_text", user_message))
        ev.append(_sse("intent", {"type": "assessment", "via": "agent_loop"}))
        result, audit = await run_assessment(session_id, symptoms)
        await _persist_assessment(result, audit)
        async for e in stream_result(result, emit_complete=False):
            ev.append(e)
        summary = {
            "ok": True,
            "assessment_id": result.assessment_id,
            "risk_level": result.risk_level,
            "advice": result.advice[:800],
            "user_input": result.user_input,
        }
        return json.dumps(summary, ensure_ascii=False), ev

    if name == "get_history":
        ev.append(_sse("intent", {"type": "history", "via": "agent_loop"}))
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
            items.append(
                HistoryItem(
                    assessment_id=doc["assessment_id"],
                    risk_level=level,
                    summary=doc["user_input"][:40],
                    rule_version=doc["rule_version"],
                    created_at=doc["created_at"],
                ).model_dump()
            )
        history_data = HistoryResponse(trend=trend, items=items).model_dump()
        ev.append(_sse("history", history_data))
        return json.dumps(
            {"ok": True, "trend": trend, "count": len(items), "summary": "见流式 history 事件"},
            ensure_ascii=False,
        ), ev

    if name == "get_result":
        aid = str(args.get("assessment_id", "latest"))
        ev.append(_sse("intent", {"type": "result", "via": "agent_loop"}))
        if aid == "latest":
            db = get_db()
            doc = await db.assessments.find_one(
                {"session_id": session_id},
                {"_id": 0},
                sort=[("created_at", -1)],
            )
        else:
            doc = await get_assessment_cache(aid)
            if not doc:
                db = get_db()
                doc = await db.assessments.find_one({"assessment_id": aid}, {"_id": 0})
        if doc:
            ev.append(_sse("result", doc))
            slim = {k: doc[k] for k in ("assessment_id", "risk_level", "advice") if k in doc}
            return json.dumps({"ok": True, "result": slim}, ensure_ascii=False), ev
        ev.append(_sse("result", {"error": "未找到评估记录"}))
        return json.dumps({"ok": False, "error": "not found"}, ensure_ascii=False), ev

    if name == "contact_team":
        reason = str(args.get("reason", ""))
        ev.append(_sse("intent", {"type": "contact", "via": "agent_loop"}))
        from datetime import datetime, timezone

        db = get_db()
        doc = {
            "session_id": session_id,
            "reason": reason or "用户请求联系医疗团队",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        inserted = await db.contact_requests.insert_one(doc)
        msg = "已为您提交医疗团队联系请求，团队会尽快与您取得联系。"
        ev.append(_sse("contact", {
            "id": str(inserted.inserted_id),
            "status": "pending",
            "message": msg,
        }))
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False), ev

    if name == "list_files":
        r = list_files_tool(str(args.get("path", "") or ""))
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "glob_files":
        r = glob_files_tool(
            str(args.get("pattern", "")),
            str(args.get("root", "") or ""),
        )
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "grep":
        r = grep_tool(
            str(args.get("pattern", "")),
            str(args.get("path", "") or ""),
            file_glob=str(args.get("file_glob", "*")),
            case_insensitive=bool(args.get("case_insensitive", True)),
        )
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "read_file":
        off = args.get("offset", 0)
        lim = args.get("limit")
        r = read_file_tool(
            str(args.get("path", "")),
            offset=int(off) if off is not None else 0,
            limit=int(lim) if lim is not None else None,
        )
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "read_document":
        r = read_document_tool(str(args.get("path", "")))
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "write_file":
        r = write_file_tool(str(args.get("path", "")), str(args.get("content", "")))
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "delete_file":
        r = delete_file_tool(str(args.get("path", "")))
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    if name == "bash":
        if not settings.ENABLE_BASH_TOOL:
            return json.dumps({"ok": False, "error": "bash disabled"}, ensure_ascii=False), ev
        r = bash_tool(str(args.get("command", "")), args.get("cwd"))
        ev.append(_sse("intent", {"type": "workspace", "tool": name}))
        ev.append(_sse("tool_result", {"tool": name, "result": r}))
        return json.dumps(r, ensure_ascii=False), ev

    return json.dumps({"ok": False, "error": f"unknown tool: {name}"}, ensure_ascii=False), ev


def _assistant_to_dict(msg: Any) -> dict[str, Any]:
    return msg.model_dump(exclude_none=True)


async def run_agent_loop(
    session_id: str,
    user_message: str,
    history: list[dict[str, str]],
) -> AsyncGenerator[dict, None]:
    """多轮工具循环；结束时发 message（若有）与 complete。"""
    client, model = router_mod._get_client()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_agent_loop_system_content()},
    ]
    for h in history:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    yield _sse("intent", {"type": "agent_loop", "max_steps": settings.AGENT_LOOP_MAX_STEPS})

    max_steps = settings.AGENT_LOOP_MAX_STEPS

    for step in range(max_steps):
        messages[0] = {"role": "system", "content": _build_agent_loop_system_content()}

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=router_mod.TOOLS,
                tool_choice="auto",
                temperature=min(0.2, float(settings.LLM_TEMPERATURE)),
            )
        except Exception as e:
            logger.exception("agent_loop completion failed: %s", e)
            yield _sse("message", {"content": f"模型调用失败：{e}"})
            yield _sse("complete", {"status": "error"})
            return

        choice = resp.choices[0].message
        if choice.tool_calls:
            messages.append(_assistant_to_dict(choice))
            for tc in choice.tool_calls:
                fn = tc.function
                tname = fn.name
                try:
                    targs = json.loads(fn.arguments) if fn.arguments else {}
                except json.JSONDecodeError:
                    targs = {}
                logger.info("agent_loop step %s tool %s %s", step, tname, targs)
                out_json, extra_ev = await _dispatch_tool(
                    tname,
                    targs,
                    session_id=session_id,
                    user_message=user_message,
                )
                for e in extra_ev:
                    yield e
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": out_json,
                })
            continue

        final_text = (choice.content or "").strip()
        if final_text:
            yield _sse("intent", {"type": "text", "via": "agent_loop"})
            yield _sse("message", {"content": final_text})
        yield _sse("complete", {"status": "done", "agent_steps": step + 1})
        return

    yield _sse("message", {"content": "已达到本轮工具步数上限，请简化请求或稍后重试。"})
    yield _sse("complete", {"status": "limit"})

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

import asyncio
import json
import logging
from datetime import datetime, timezone
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from server.cache import get_assessment_cache, set_assessment_cache
from server.db import get_db
from server.engine.agent import run_assessment
from server.engine.executor import stream_result
from server.engine.agent_loop import run_agent_loop
from server.engine.rag_store import save_user_feedback
from server.engine.router import route
from server.engine.summarizer import summarize_session
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
from server.models import ChatRequest, HistoryItem, HistoryResponse, SessionRequest, UserFeedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _handle_assessment(
    session_id: str,
    user_token: str,
    symptoms_text: str,
    parent_session_id: str = "admin",
) -> AsyncGenerator[dict, None]:
    """执行评估并流式输出结果。"""
    yield _sse("intent", {"type": "assessment"})

    result, audit = await run_assessment(
        session_id, symptoms_text, user_token=user_token, parent_session_id=parent_session_id
    )

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


def _format_read_file(r: dict) -> str:
    if not r.get("ok"):
        return f"读取文件失败：{r.get('error', 'unknown')}"
    path = r.get("path", "")
    start = int(r.get("offset", 0)) + 1
    end = start + int(r.get("lines", 0)) - 1
    nlines = r.get("total_lines", 0)
    head = f"**{path}** 第 {start}–{end} 行（共 {nlines} 行）"
    if r.get("truncated_bytes"):
        head += "；文件过大已按字节截断"
    return f"{head}\n\n```\n{r.get('content', '')}\n```"


def _format_bash(r: dict) -> str:
    if r.get("error"):
        return f"命令执行失败：{r.get('error')}"
    status = "成功" if r.get("ok") else f"退出码 {r.get('exit_code')}"
    cwd = r.get("cwd", ".")
    out = r.get("output", "")
    return f"**bash**（cwd: `{cwd}`）{status}\n\n```\n{out}\n```"


def _format_list_files(r: dict) -> str:
    if not r.get("ok"):
        return f"列出目录失败：{r.get('error', 'unknown')}"
    return f"**{r.get('path', '.')}**\n\n```\n{r.get('listing', '')}\n```"


def _format_read_document(r: dict) -> str:
    if not r.get("ok"):
        return f"读取文档失败：{r.get('error', 'unknown')}"
    body = r.get("content", "")
    if r.get("truncated"):
        body += "\n\n（输出已截断）"
    return f"**{r.get('path', '')}**\n\n```\n{body}\n```"


def _format_write_file(r: dict) -> str:
    if not r.get("ok"):
        return f"写入失败：{r.get('error', 'unknown')}"
    return f"已写入 `{r.get('path', '')}`（{r.get('bytes_written', 0)} 字节）"


def _format_delete_file(r: dict) -> str:
    if not r.get("ok"):
        return f"删除失败：{r.get('error', 'unknown')}"
    return f"已删除 `{r.get('path', '')}`"


def _format_grep(r: dict) -> str:
    if not r.get("ok"):
        return f"grep 失败：{r.get('error', 'unknown')}"
    lines = [f"模式 `{r.get('pattern')}` 在 `{r.get('path')}` 下共 {r.get('match_count', 0)} 处匹配："]
    for m in r.get("matches") or []:
        lines.append(f"- `{m.get('path')}`:{m.get('line')}  {m.get('text', '')}")
    if r.get("truncated"):
        lines.append("\n（结果已截断，请缩小 path 或收紧 pattern）")
    return "\n".join(lines)


def _format_glob_files(r: dict) -> str:
    if not r.get("ok"):
        return f"glob 失败：{r.get('error', 'unknown')}"
    paths = r.get("paths") or []
    body = "\n".join(f"- `{p}`" for p in paths[:200])
    if len(paths) > 200:
        body += f"\n… 共 {len(paths)} 条（仅展示前 200）"
    if r.get("truncated"):
        body += "\n（已截断，请细化 glob）"
    return f"**{r.get('root', '.')}` / `{r.get('pattern')}`**\n\n{body or '（无匹配）'}"


async def _handle_workspace_tool(tool: str, args: dict) -> AsyncGenerator[dict, None]:
    """actone 风格工作区工具 → SSE message + tool_result。"""
    yield _sse("intent", {"type": "workspace", "tool": tool})

    if tool == "list_files":
        r = list_files_tool(str(args.get("path", "") or ""))
        text = _format_list_files(r)
    elif tool == "read_file":
        offset = args.get("offset", 0)
        limit = args.get("limit")
        r = read_file_tool(
            str(args.get("path", "")),
            offset=int(offset) if offset is not None else 0,
            limit=int(limit) if limit is not None else None,
        )
        text = _format_read_file(r)
    elif tool == "read_document":
        r = read_document_tool(str(args.get("path", "")))
        text = _format_read_document(r)
    elif tool == "write_file":
        r = write_file_tool(str(args.get("path", "")), str(args.get("content", "")))
        text = _format_write_file(r)
    elif tool == "delete_file":
        r = delete_file_tool(str(args.get("path", "")))
        text = _format_delete_file(r)
    elif tool == "grep":
        r = grep_tool(
            str(args.get("pattern", "")),
            str(args.get("path", "") or ""),
            file_glob=str(args.get("file_glob", "*")),
            case_insensitive=bool(args.get("case_insensitive", True)),
        )
        text = _format_grep(r)
    elif tool == "glob_files":
        r = glob_files_tool(
            str(args.get("pattern", "")),
            str(args.get("root", "") or ""),
        )
        text = _format_glob_files(r)
    elif tool == "bash":
        r = bash_tool(str(args.get("command", "")), args.get("cwd"))
        text = _format_bash(r)
    else:
        r = {"ok": False, "error": "unknown tool"}
        text = "未知工作区工具"

    yield _sse("message", {"content": text})
    yield _sse("tool_result", {"tool": tool, "result": r})
    yield _sse("complete", {"status": "done"})


async def _chat_stream_single_shot(req: ChatRequest) -> AsyncGenerator[dict, None]:
    """单跳 route：一次模型调用 → 至多执行一个工具。"""
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

    if tool == "assess_symptoms":
        # Skill: 完整评估流程（submit_assessment → 持久化 → 取结果 → 流式展示）
        symptoms_text = args.get("symptoms_text", req.message)
        async for event in _handle_assessment(
            req.session_id, req.user_token, symptoms_text, req.parent_session_id
        ):
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

    elif tool in (
        "list_files",
        "read_file",
        "read_document",
        "write_file",
        "delete_file",
        "grep",
        "glob_files",
        "bash",
    ):
        async for event in _handle_workspace_tool(tool, args):
            yield event

    else:
        # 未知 tool → 降级为文本
        async for event in _handle_text(decision.text or "抱歉，我没有理解您的意思。"):
            yield event


async def chat_stream(req: ChatRequest) -> AsyncGenerator[dict, None]:
    """根据 use_agent_loop：多轮 agent loop 或单跳 legacy。"""
    if req.use_agent_loop:
        try:
            async for event in run_agent_loop(
                req.session_id, req.user_token, req.message, req.history, req.parent_session_id
            ):
                yield event
        except Exception as e:
            logger.exception("agent_loop failed, falling back to single-shot: %s", e)
            async for event in _chat_stream_single_shot(req):
                yield event
        return
    async for event in _chat_stream_single_shot(req):
        yield event


@router.post("/chat")
async def chat(req: ChatRequest):
    """统一对话入口 — SSE 流式响应。"""
    return EventSourceResponse(chat_stream(req))


@router.post("/feedback")
async def post_feedback(doc: UserFeedback):
    db = get_db()
    await save_user_feedback(db, doc)
    return {"ok": True}


@router.post("/session/summarize")
async def summarize(req: SessionRequest):
    db = get_db()
    asyncio.create_task(summarize_session(db, req.session_id, req.user_token))
    return {"ok": True, "queued_at": datetime.now(timezone.utc).isoformat()}

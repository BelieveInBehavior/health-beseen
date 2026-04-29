"""
LLM Tool-Use Router — 意图识别 + 工具选择。

用 OpenAI function calling 让 LLM 根据用户消息决定：
- 调用 tool (submit_assessment / get_result / get_history / contact_team)
- 或直接文本回复（追问 / 闲聊）

LLM 不可用时降级为本地关键词路由。
"""

from __future__ import annotations

import json
import logging

from openai import AsyncAzureOpenAI, AsyncOpenAI

from server.config import settings
from server.models import RouterDecision

logger = logging.getLogger(__name__)

# ──────────────────── System Prompt ────────────────────

ROUTER_SYSTEM_PROMPT = """\
你是乳腺癌治疗副作用评估助手。你的职责是根据用户消息选择合适的操作：

1. 当用户描述了明确的身体症状或副作用时，调用 submit_assessment 进行评估
2. 当用户想查看某次特定的评估结果时，调用 get_result（需要 assessment_id）
3. 当用户想查看历史记录、之前的评估、评估趋势时，直接调用 get_history（无需参数，系统会自动按用户身份查询）
4. 当用户想联系医疗团队或医生时，调用 contact_team
5. 当用户描述不够明确时，用文字追问以收集更多信息（不调用任何工具）
6. 当用户打招呼或闲聊时，友好回复并引导描述症状

重要规则：
- 如果用户只说"不舒服""不太好"等模糊描述，先追问具体症状，不要直接评估
- 从整个对话上下文提取症状，不仅是最后一条消息
- 调用 submit_assessment 时，symptoms_text 应包含从对话中提取的所有症状描述
- 用户说"之前的评估""历史记录""看看记录"时，直接调用 get_history，不需要追问 ID
- 用中文回复，语气温和专业
"""

# ──────────────────── Tools Schema ────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_assessment",
            "description": "用户描述了身体不适或副作用症状，需要进行风险评估。当用户明确描述了症状时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symptoms_text": {
                        "type": "string",
                        "description": "从对话中提取的完整症状描述",
                    }
                },
                "required": ["symptoms_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_result",
            "description": "用户想查看某次已完成的评估结果详情。",
            "parameters": {
                "type": "object",
                "properties": {
                    "assessment_id": {
                        "type": "string",
                        "description": "评估记录 ID",
                    }
                },
                "required": ["assessment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_history",
            "description": "用户想查看过往评估记录列表或历史趋势。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contact_team",
            "description": "用户明确表达想联系医疗团队或医生。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "联系原因",
                    }
                },
            },
        },
    },
]

# ──────────────────── LLM Client ────────────────────


def _get_client() -> tuple[AsyncAzureOpenAI | AsyncOpenAI, str]:
    """返回 (client, model_or_deployment)。复用 planner 相同的配置。"""
    if settings.LLM_PROVIDER == "azure":
        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        return client, settings.AZURE_OPENAI_DEPLOYMENT
    else:
        client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY or settings.AZURE_OPENAI_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        return client, settings.LLM_MODEL


# ──────────────────── Route Function ────────────────────


async def route(message: str, history: list[dict[str, str]], session_id: str) -> RouterDecision:
    """
    调用 LLM (with tools) 进行意图识别和工具选择。

    Returns:
        RouterDecision: tool_call 或 text 回复。
    """
    try:
        return await _llm_route(message, history)
    except Exception as e:
        logger.warning("LLM router failed, using fallback: %s", e)
        return _fallback_route(message)


async def _llm_route(message: str, history: list[dict[str, str]]) -> RouterDecision:
    """通过 LLM function calling 进行路由决策。"""
    client, model = _get_client()

    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1,
    )

    choice = resp.choices[0].message
    if choice.tool_calls:
        tc = choice.tool_calls[0]
        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        return RouterDecision(
            type="tool_call",
            tool_name=tc.function.name,
            tool_args=args,
            text=choice.content or "",
        )

    # Some models embed tool calls in text content instead of tool_calls
    content = choice.content or ""
    parsed_call = _parse_text_tool_call(content)
    if parsed_call:
        return parsed_call

    return RouterDecision(
        type="text",
        text=content or "请问您有什么不适症状需要我帮您评估？",
    )


# ──────────────────── Text Tool-Call Parser ────────────────────

_VALID_TOOLS = {"submit_assessment", "get_result", "get_history", "contact_team"}


def _parse_text_tool_call(content: str) -> RouterDecision | None:
    """
    Some models embed function calls in text content like:
    {"name":"functions.get_history","arguments":{}}
    Parse these and convert to RouterDecision.
    """
    # Try parsing first line as JSON
    first_line = content.split("\n")[0].strip()
    obj = None
    for candidate in [first_line, content.strip()]:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "name" in parsed:
                obj = parsed
                break
        except (json.JSONDecodeError, ValueError):
            continue

    if obj is None:
        return None

    name = obj.get("name", "")
    # Strip "functions." prefix if present
    if name.startswith("functions."):
        name = name[len("functions."):]

    if name not in _VALID_TOOLS:
        return None

    args = obj.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}

    # Extract remaining text (strip the JSON part)
    remaining = content.replace(match.group(), "").strip()
    logger.info("Parsed text tool call: %s(%s)", name, args)

    return RouterDecision(
        type="tool_call",
        tool_name=name,
        tool_args=args,
        text=remaining,
    )


# ──────────────────── Fallback Router ────────────────────

_SYMPTOM_KEYWORDS = [
    "疼", "痛", "发烧", "发热", "恶心", "呕吐", "红疹", "皮疹",
    "呼吸困难", "胸闷", "胸痛", "出血", "腹泻", "头痛", "乏力",
    "疲劳", "失眠", "麻木", "肿痛", "低烧", "高烧", "咯血",
    "便血", "吐血", "心悸", "过敏", "水泡", "破溃", "脱皮",
    "食欲", "吃不下",
]

_HISTORY_KEYWORDS = ["历史", "记录", "之前", "上次", "以前", "趋势"]

_CONTACT_KEYWORDS = ["联系", "医生", "团队", "预约", "约一下", "打电话"]

_RESULT_KEYWORDS = ["结果", "评估结果", "再看一下", "刚才的"]


def _fallback_route(message: str) -> RouterDecision:
    """LLM 不可用时的本地关键词降级路由。"""
    # 查历史
    if any(kw in message for kw in _HISTORY_KEYWORDS):
        return RouterDecision(type="tool_call", tool_name="get_history")

    # 查结果
    if any(kw in message for kw in _RESULT_KEYWORDS):
        return RouterDecision(
            type="tool_call",
            tool_name="get_result",
            tool_args={"assessment_id": "latest"},
        )

    # 联系团队
    if any(kw in message for kw in _CONTACT_KEYWORDS):
        return RouterDecision(
            type="tool_call",
            tool_name="contact_team",
            tool_args={"reason": message},
        )

    # 症状关键词 → 评估
    if any(kw in message for kw in _SYMPTOM_KEYWORDS):
        return RouterDecision(
            type="tool_call",
            tool_name="submit_assessment",
            tool_args={"symptoms_text": message},
        )

    # 默认文本回复
    return RouterDecision(
        type="text",
        text="请问您有什么不适症状需要我帮您评估？您可以描述症状的具体表现、出现时间和严重程度。",
    )

"""
LLM Tool-Use Router — 意图识别 + 工具选择。

用 OpenAI function calling 让 LLM 根据用户消息决定：
- 调用 tool（assess_symptoms / get_result / get_history / contact_team / list_files / glob_files /
  read_file / read_document / write_file / delete_file / grep / bash）
- 或直接文本回复（追问 / 闲聊）

Skills：与 OpenClaw 一致，不把「读 skill」做成单独工具；可用 skill 列表由服务端注入 system 的
`<available_skills>`，模型用 **read_file** 读取其中 path（SKILL.md）即可。

LLM 不可用时降级为本地关键词路由。
"""

from __future__ import annotations

import json
import logging

from openai import AsyncAzureOpenAI, AsyncOpenAI

from server.config import settings
from server.engine.skills_prompt import build_openclaw_skills_section
from server.models import RouterDecision

logger = logging.getLogger(__name__)

# ──────────────────── System Prompt ────────────────────

ROUTER_SYSTEM_BASE = """\
你是乳腺癌治疗副作用评估助手。你有以下能力可以使用：

【Skill】assess_symptoms — 完整的症状评估流程（主路径）
  当用户明确描述了身体不适或副作用症状时调用。内部会自动完成评估、取结果、展示全流程。

【Tool】get_result — 查看某次已完成的评估结果
  需要用户提到具体的 assessment_id。

【Tool】get_history — 查看历史评估记录和趋势
  用户说"之前的记录""历史""看看以前的"时调用，无需参数。

【Tool】contact_team — 联系医疗团队
  用户明确表达想联系医生或医疗团队时调用。

【Tool】list_files — 列出工作区内某目录下的子目录与文件（path 相对根，空字符串表示根目录）。
  查看 skill 目录下 scripts/ 等时使用（对齐 actone-ai）。

【Tool】glob_files — 在工作区内按 glob 枚举路径（如 `**/*.py`），不经过 shell，比 bash 更安全。

【Tool】grep — 在工作区内用正则搜索文本（Python re），适合在代码树中找符号；大目录会截断结果。

【Tool】read_file — 读取工作区内文本文件（path 相对项目根，可选 offset/limit 按行分页）。
  读取 Skill 全文时 path 用下方技能索引表「File」列或 `<available_skills>` 的 path。

【Tool】read_document — 从 PDF / DOCX / XLSX 抽取文本（需安装可选依赖；纯文本仍推荐 read_file）。

【Tool】write_file — 在工作区内创建或覆盖文本文件（path + content）；受 WORKSPACE_WRITE_ENABLED 控制。

【Tool】delete_file — 删除工作区内单个文件（非目录）；部分路径受保护（如 .env）。

【Tool】bash — 在工作区下执行 shell（/bin/bash -lc，可选 cwd 为相对项目根的子目录）
  用于构建、测试、git、管道等；搜索代码优先用 **grep** / **glob_files**，读文件用 **read_file**。

【直接回复（不调用任何工具）】
  当用户描述不够明确时，追问具体症状。
  当用户打招呼时，友好回复并引导描述症状。

重要规则：
- 如果用户只说"不舒服""不太好"等模糊描述，先追问具体症状，不要直接评估
- 从整个对话上下文提取症状，不仅是最后一条消息
- 调用 assess_symptoms 时，symptoms_text 应包含从对话中提取的所有症状描述
- 用户说"之前的评估""历史记录""看看记录"时，直接调用 get_history，不需要追问 ID
- 用中文回复，语气温和专业
"""


def build_router_system_content() -> str:
    """注入 OpenClaw 式 skills 区块 + 医疗路由基座。"""
    return ROUTER_SYSTEM_BASE + "\n" + build_openclaw_skills_section()

# ──────────────────── Tools Schema ────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "assess_symptoms",
            "description": "【主路径 Skill】用户描述了身体不适或副作用症状，需要完整的风险评估流程（评估 → 取结果 → 展示）。当用户明确描述了症状时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symptoms_text": {
                        "type": "string",
                        "description": "从对话中提取的完整症状描述，包含对话历史中所有相关症状",
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
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "列出工作区内目录内容（actone-ai list_files）。path 为相对项目根的目录，"
                "空字符串表示根目录；用于浏览 skills/ 子目录、源码树等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，如 skills、skills/my_skill；默认可传空字符串表示根",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": (
                "在工作区内按 glob 模式列出相对路径（不执行 shell）。"
                "例如 pattern=`**/*.py`、root=`server`。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "glob，如 **/*.md、server/**/*.py"},
                    "root": {
                        "type": "string",
                        "description": "相对工作区的起始目录，默认空为仓库根",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取工作区内的文本文件（相对项目根路径）。"
                "读取 SKILL 说明：使用系统提示中技能索引表的 File 列或 <available_skills> 的 path。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对项目根的文件路径，如 README.md"},
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（从 0 计），可选",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多读取行数，可选",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": (
                "从 PDF、DOCX、XLSX 提取文本（actone-ai read_document）。"
                "纯文本/markdown 请优先 read_file。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对项目根的文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "在工作区内写入或覆盖文本文件（actone-ai write_file）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对项目根的文件路径"},
                    "content": {"type": "string", "description": "文件完整内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除工作区内单个文件，不能删除目录（actone-ai delete_file）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对项目根的文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "在工作区用正则搜索文件内容（非 shell 的 grep，避免注入）。"
                "path 为文件或目录（相对根）；目录下会跳过 .git/.venv 等；file_glob 过滤文件名如 *.py。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python 正则表达式"},
                    "path": {
                        "type": "string",
                        "description": "相对工作区的文件或目录，默认可为空表示从仓库根递归",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "文件名 glob，默认 *",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写，默认 true",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在项目工作区内执行 bash 命令（shell -lc）。用于 git status、运行脚本、构建等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "cwd": {
                        "type": "string",
                        "description": "相对项目根的工作子目录，可选，默认项目根",
                    },
                },
                "required": ["command"],
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

    messages = [{"role": "system", "content": build_router_system_content()}]
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

_VALID_TOOLS = {
    "assess_symptoms",
    "get_result",
    "get_history",
    "contact_team",
    "list_files",
    "glob_files",
    "read_file",
    "read_document",
    "write_file",
    "delete_file",
    "grep",
    "bash",
}


def _parse_text_tool_call(content: str) -> RouterDecision | None:
    """
    Some models embed function calls in text content like:
    {"name":"functions.get_history","arguments":{}}
    Parse these and convert to RouterDecision.
    """
    # Try parsing first line as JSON
    first_line = content.split("\n")[0].strip()
    obj = None
    matched_prefix = ""
    for candidate in [first_line, content.strip()]:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "name" in parsed:
                obj = parsed
                matched_prefix = candidate
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

    full = content.strip()
    remaining = full[len(matched_prefix):].strip() if matched_prefix and full.startswith(matched_prefix) else ""
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

    # 症状关键词 → assess_symptoms skill
    if any(kw in message for kw in _SYMPTOM_KEYWORDS):
        return RouterDecision(
            type="tool_call",
            tool_name="assess_symptoms",
            tool_args={"symptoms_text": message},
        )

    # 默认文本回复
    return RouterDecision(
        type="text",
        text="请问您有什么不适症状需要我帮您评估？您可以描述症状的具体表现、出现时间和严重程度。",
    )

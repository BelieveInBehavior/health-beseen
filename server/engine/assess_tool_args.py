"""assess_symptoms 工具参数：在执行边界规范化（对齐 actone execute_tool 对 arguments 的处理）。"""

from __future__ import annotations

from typing import Any

_DEFAULT = "未指定"


def normalize_assess_symptoms_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """
    将 LLM 解析后的 tool arguments 规整为结构化字段。
    兼容 symptoms 传入 string（部分模型不按 schema 出数组）。
    """
    raw = arguments.get("symptoms")
    symptoms: list[str] = []
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            symptoms = [s]
    elif isinstance(raw, list):
        symptoms = [str(x).strip() for x in raw if str(x).strip()]

    loc = arguments.get("location")
    dur = arguments.get("duration")
    location = str(loc).strip() if loc is not None else _DEFAULT
    duration = str(dur).strip() if dur is not None else _DEFAULT
    if not location:
        location = _DEFAULT
    if not duration:
        duration = _DEFAULT

    return {"symptoms": symptoms, "location": location, "duration": duration}


def merge_assess_symptoms_to_user_input(
    arguments: dict[str, Any],
    fallback_user_text: str,
) -> str:
    """
    run_assessment 仍消费自然语言 user_input：将结构化字段拼成一条，
    perception/rules 链路无需改动。symptoms 为空时回退到最后一条用户原文。
    """
    norm = normalize_assess_symptoms_arguments(arguments)
    if norm["symptoms"]:
        return (
            f"症状：{'、'.join(norm['symptoms'])}；"
            f"部位：{norm['location']}；持续时间：{norm['duration']}"
        )
    return fallback_user_text

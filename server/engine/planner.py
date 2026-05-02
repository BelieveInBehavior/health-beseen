"""
LLM Augment (Planner) — 当规则引擎 confidence < 0.6 时调用 LLM 辅助判断。
支持 Azure OpenAI / OpenAI / OpenRouter 三种 provider。
失败时降级为 heuristic 回复。
"""

from __future__ import annotations

import logging

from openai import AsyncAzureOpenAI, AsyncOpenAI

from server.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""你是一个{settings.ASSISTANT_SYSTEM_ROLE}。你需要根据患者描述的症状，给出：
1. 风险等级（high / mid / low）
2. 下一步建议（具体可执行的医疗建议）
3. 参考依据（引用指南或知识库来源）

风险分级标准：
- high：需要立即就医或24小时内联系医疗团队的紧急情况
- mid：需要联系团队评估或密切观察的情况
- low：可以继续观察并在复诊时反馈的情况

请用JSON格式回复：
{{"risk_level": "high|mid|low", "advice": "具体建议", "evidence": "参考来源"}}
"""


def _get_client() -> tuple[AsyncAzureOpenAI | AsyncOpenAI, str]:
    """返回 (client, model_or_deployment)。"""
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


async def augment(user_input: str, symptoms: list[str]) -> dict:
    """
    调用 LLM 对症状进行辅助评估。
    返回 {"risk_level": str, "advice": str, "evidence": str, "used_llm": True}。
    失败时返回 heuristic 降级结果。
    """
    try:
        client, model = _get_client()
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"患者描述：{user_input}\n抽取症状：{', '.join(symptoms)}"},
            ],
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            top_p=settings.LLM_TOP_P,
            response_format={"type": "json_object"},
        )
        import json
        content = resp.choices[0].message.content or "{}"
        result = json.loads(content)
        return {
            "risk_level": result.get("risk_level", "mid"),
            "advice": result.get("advice", "建议联系医疗团队进一步评估。"),
            "evidence": result.get("evidence", "LLM辅助评估"),
            "used_llm": True,
        }
    except Exception as e:
        logger.warning("LLM augment failed, falling back to heuristic: %s", e)
        return _heuristic_fallback(symptoms)


def _heuristic_fallback(symptoms: list[str]) -> dict:
    """LLM 不可用时的本地降级逻辑。"""
    if not symptoms:
        return {
            "risk_level": "low",
            "advice": "您描述的症状暂未匹配到已知的风险模式。建议继续观察，如有不适加重请及时就医。",
            "evidence": "本地 heuristic 评估（LLM 不可用）",
            "used_llm": False,
        }
    return {
        "risk_level": "mid",
        "advice": f"检测到以下症状：{'、'.join(symptoms)}。建议联系您的医疗团队进行进一步评估。",
        "evidence": "本地 heuristic 评估（LLM 不可用）",
        "used_llm": False,
    }

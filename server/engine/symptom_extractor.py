"""
使用 Claude API tool_use 功能自动提取结构化症状信息

症状评估工具定义：
- 症状列表（symptoms）
- 症状部位（location）
- 持续时间（duration）
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import Anthropic

from server.config import settings

logger = logging.getLogger(__name__)

# Claude API 客户端（单例）
_claude_client: Anthropic | None = None


def get_claude_client() -> Anthropic:
    """获取或初始化 Claude 客户端"""
    global _claude_client
    if _claude_client is None:
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        _claude_client = Anthropic(api_key=api_key)
    return _claude_client


# 工具定义
ASSESS_TOOL_DEFINITION = {
    "name": "assess",
    "description": "评估患者症状风险等级并提取结构化信息",
    "input_schema": {
        "type": "object",
        "properties": {
            "symptoms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "症状列表，如 ['胸闷', '发热']"
            },
            "location": {
                "type": "string",
                "description": "症状部位，如 '胸口'、'腹部'、'全身'，无法确定时填 '未指定'"
            },
            "duration": {
                "type": "string",
                "description": "持续时间，如 '两天'、'三小时'、'一周'，无法确定时填 '未指定'"
            }
        },
        "required": ["symptoms", "location", "duration"]
    }
}


class StructuredSymptom:
    """结构化症状数据模型"""
    def __init__(
        self,
        symptoms: list[str],
        location: str,
        duration: str,
        confidence: float = 1.0,
    ):
        self.symptoms = symptoms
        self.location = location
        self.duration = duration
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "symptoms": self.symptoms,
            "location": self.location,
            "duration": self.duration,
            "confidence": self.confidence,
        }

    def __repr__(self) -> str:
        return f"StructuredSymptom(symptoms={self.symptoms}, location={self.location}, duration={self.duration})"


async def assess_symptoms(user_input: str, model: str = "claude-3-5-sonnet-20241022") -> StructuredSymptom:
    """
    使用 Claude API tool_use 功能从自然语言输入中提取结构化症状信息。

    Args:
        user_input: 用户输入的自然语言文本，例如："我这两天胸口很闷，还有点发热"
        model: 使用的 Claude 模型，默认为最新的 Sonnet 模型

    Returns:
        StructuredSymptom: 包含结构化症状信息的对象

    Raises:
        ValueError: 如果模型未能调用工具或解析失败
    """
    client = get_claude_client()

    system_prompt = """你是一个医疗症状提取助手。
用户会向你描述他们的症状。你需要使用 assess 工具来提取以下信息：
1. 症状列表：从用户描述中识别出所有具体症状
2. 症状部位：确定症状发生在身体的哪个部位
3. 持续时间：提取症状已经持续的时间

如果某些信息无法从用户输入中确定，请使用 '未指定'。
请确保每次调用工具时提供准确和完整的信息。"""

    messages = [
        {
            "role": "user",
            "content": f"请提取我的症状信息：{user_input}"
        }
    ]

    try:
        # 调用 Claude API，启用工具使用
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            tools=[ASSESS_TOOL_DEFINITION],
            messages=messages,
        )

        # 查找工具调用
        tool_use_block = None
        for content_block in response.content:
            if content_block.type == "tool_use" and content_block.name == "assess":
                tool_use_block = content_block
                break

        if not tool_use_block:
            logger.warning(f"No tool_use block found in response for input: {user_input}")
            # 降级：使用旧的关键词提取方法
            from server.engine.perception import extract_symptoms
            symptoms = extract_symptoms(user_input)
            return StructuredSymptom(
                symptoms=symptoms,
                location="未指定",
                duration="未指定",
                confidence=0.5,
            )

        # 解析工具调用结果
        input_data = tool_use_block.input
        logger.info(f"Tool use result: {input_data}")

        return StructuredSymptom(
            symptoms=input_data.get("symptoms", []),
            location=input_data.get("location", "未指定"),
            duration=input_data.get("duration", "未指定"),
            confidence=1.0,
        )

    except Exception as e:
        logger.error(f"Error in assess_symptoms: {e}")
        # 降级：使用旧的关键词提取方法
        from server.engine.perception import extract_symptoms
        symptoms = extract_symptoms(user_input)
        return StructuredSymptom(
            symptoms=symptoms,
            location="未指定",
            duration="未指定",
            confidence=0.3,
        )

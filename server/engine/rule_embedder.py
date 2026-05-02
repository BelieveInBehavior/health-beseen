from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncAzureOpenAI, AsyncOpenAI

from server.config import settings
from server.engine.rules import ALL_RULES, RULE_VERSION

logger = logging.getLogger(__name__)

_RULE_EMBEDDINGS: list[dict] = []


def _get_embed_client() -> tuple[AsyncAzureOpenAI | AsyncOpenAI, str]:
    if settings.LLM_PROVIDER == "azure":
        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        return client, settings.EMBEDDING_MODEL
    client = AsyncOpenAI(
        api_key=settings.LLM_API_KEY or settings.AZURE_OPENAI_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )
    return client, settings.EMBEDDING_MODEL


async def get_embedding(text: str, client: AsyncAzureOpenAI | AsyncOpenAI | None = None) -> list[float]:
    if not text.strip():
        return []
    c = client
    model = settings.EMBEDDING_MODEL
    if c is None:
        c, model = _get_embed_client()
    resp = await c.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def _cache_path() -> Path:
    return Path(settings.RULE_EMBEDDINGS_CACHE)


def load_rule_embeddings() -> list[dict]:
    path = _cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("rule_version") != RULE_VERSION:
            return []
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return rows
    except Exception as e:
        logger.warning("load rule embeddings failed: %s", e)
    return []


def save_rule_embeddings(rows: list[dict]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rule_version": RULE_VERSION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


async def precompute_rule_embeddings(force: bool = False) -> list[dict]:
    global _RULE_EMBEDDINGS
    if _RULE_EMBEDDINGS and not force:
        return _RULE_EMBEDDINGS

    cached = load_rule_embeddings()
    if cached and not force:
        _RULE_EMBEDDINGS = cached
        return _RULE_EMBEDDINGS

    try:
        client, _ = _get_embed_client()
        rows: list[dict] = []
        for rule in ALL_RULES:
            text = f"keywords: {' '.join(rule.keywords)}\nadvice: {rule.advice}\nevidence: {rule.evidence}"
            emb = await get_embedding(text, client)
            rows.append({"rule_id": rule.id, "embedding": emb})
        save_rule_embeddings(rows)
        _RULE_EMBEDDINGS = rows
        return _RULE_EMBEDDINGS
    except Exception as e:
        logger.warning("precompute rule embeddings failed: %s", e)
        _RULE_EMBEDDINGS = []
        return _RULE_EMBEDDINGS


def get_rule_embeddings_in_memory() -> list[dict]:
    return _RULE_EMBEDDINGS

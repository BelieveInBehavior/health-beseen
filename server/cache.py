from __future__ import annotations

import json

import redis.asyncio as aioredis

from server.config import settings

_pool: aioredis.Redis | None = None

# TTL constants (seconds)
L1_TTL = 300      # assessment result cache — 5 min
L2_TTL = 3600     # rule cache — 1 hour
L3_TTL = 1800     # session state — 30 min


async def init_redis() -> None:
    global _pool
    _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await _pool.ping()


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.aclose()


def _r() -> aioredis.Redis:
    assert _pool is not None, "Redis not initialized"
    return _pool


# --- L1: Assessment result cache ---

async def get_assessment_cache(assessment_id: str) -> dict | None:
    raw = await _r().get(f"l1:assess:{assessment_id}")
    return json.loads(raw) if raw else None


async def set_assessment_cache(assessment_id: str, data: dict) -> None:
    await _r().set(f"l1:assess:{assessment_id}", json.dumps(data, ensure_ascii=False), ex=L1_TTL)


# --- L2: Rule cache ---

async def get_rules_cache() -> list | None:
    raw = await _r().get("l2:rules")
    return json.loads(raw) if raw else None


async def set_rules_cache(rules: list) -> None:
    await _r().set("l2:rules", json.dumps(rules, ensure_ascii=False), ex=L2_TTL)


# --- L3: Session state ---

async def get_session(session_id: str) -> dict | None:
    raw = await _r().get(f"l3:session:{session_id}")
    return json.loads(raw) if raw else None


async def set_session(session_id: str, data: dict) -> None:
    await _r().set(f"l3:session:{session_id}", json.dumps(data, ensure_ascii=False), ex=L3_TTL)

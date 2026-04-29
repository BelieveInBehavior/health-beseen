"""
File-system Memory — 每次评估写入 JSON + 更新聚合统计。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from server.models import AssessmentResult

STORE_DIR = Path(__file__).parent / "store"


def _ensure_dir() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def save_assessment(result: AssessmentResult) -> str:
    """将评估结果写入 JSON 文件，返回文件路径。"""
    _ensure_dir()
    filename = f"{result.assessment_id}.json"
    filepath = STORE_DIR / filename
    filepath.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _update_stats(result)
    return str(filepath)


def _update_stats(result: AssessmentResult) -> None:
    """更新 _stats.json 聚合统计。"""
    stats_path = STORE_DIR / "_stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
    else:
        stats = {"total": 0, "high": 0, "mid": 0, "low": 0, "last_updated": ""}

    stats["total"] += 1
    stats[result.risk_level] = stats.get(result.risk_level, 0) + 1
    stats["last_updated"] = datetime.now(timezone.utc).isoformat()

    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

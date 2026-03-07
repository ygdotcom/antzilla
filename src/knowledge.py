"""Factory knowledge — cross-business learning queries.

Every agent that generates content (outreach, playbooks, scoring) should
call query_knowledge() first to benefit from accumulated insights.
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

from src.db import SessionLocal

logger = structlog.get_logger()


async def query_knowledge(
    *,
    category: str | None = None,
    vertical: str | None = None,
    limit: int = 20,
    min_confidence: float = 0.3,
) -> list[dict]:
    """Query factory_knowledge for relevant insights.

    Returns insights matching the category/vertical, ordered by confidence.
    Includes universal insights (vertical IS NULL) alongside vertical-specific ones.
    """
    async with SessionLocal() as db:
        conditions = ["confidence >= :min_conf"]
        params: dict = {"min_conf": min_confidence, "limit": limit}

        if category:
            conditions.append("category = :cat")
            params["cat"] = category

        if vertical:
            conditions.append("(vertical = :vert OR vertical IS NULL)")
            params["vert"] = vertical
        
        where = " AND ".join(conditions)
        rows = (
            await db.execute(
                text(
                    f"SELECT id, category, vertical, insight, data, confidence, "
                    f"times_applied, times_successful "
                    f"FROM factory_knowledge WHERE {where} "
                    f"ORDER BY confidence DESC LIMIT :limit"
                ),
                params,
            )
        ).fetchall()

    return [
        {
            "id": r.id,
            "category": r.category,
            "vertical": r.vertical,
            "insight": r.insight,
            "data": r.data if isinstance(r.data, dict) else json.loads(r.data),
            "confidence": r.confidence,
            "times_applied": r.times_applied,
            "times_successful": r.times_successful,
        }
        for r in rows
    ]


async def store_knowledge(
    *,
    category: str,
    insight: str,
    data: dict,
    vertical: str | None = None,
    confidence: float = 0.5,
    source_business_id: int | None = None,
) -> int:
    """Store a new insight in the factory's long-term memory.

    Returns the inserted row ID.
    """
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "INSERT INTO factory_knowledge "
                    "(category, vertical, insight, data, confidence, source_business_id) "
                    "VALUES (:cat, :vert, :insight, :data, :conf, :biz) "
                    "RETURNING id"
                ),
                {
                    "cat": category,
                    "vert": vertical,
                    "insight": insight,
                    "data": json.dumps(data),
                    "conf": confidence,
                    "biz": source_business_id,
                },
            )
        ).fetchone()
        await db.commit()

    logger.info("knowledge_stored", category=category, vertical=vertical, confidence=confidence)
    return row.id


async def record_knowledge_usage(knowledge_id: int, *, success: bool) -> None:
    """Record that a knowledge entry was applied. Adjusts confidence over time."""
    async with SessionLocal() as db:
        if success:
            await db.execute(
                text(
                    "UPDATE factory_knowledge SET "
                    "times_applied = times_applied + 1, "
                    "times_successful = times_successful + 1, "
                    "confidence = LEAST(1.0, confidence + 0.02), "
                    "updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {"id": knowledge_id},
            )
        else:
            await db.execute(
                text(
                    "UPDATE factory_knowledge SET "
                    "times_applied = times_applied + 1, "
                    "confidence = GREATEST(0.1, confidence - 0.01), "
                    "updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {"id": knowledge_id},
            )
        await db.commit()


def format_knowledge_for_prompt(insights: list[dict]) -> str:
    """Format knowledge entries into a text block for LLM prompts."""
    if not insights:
        return ""

    lines = ["CONNAISSANCES ACCUMULÉES PAR LA FACTORY (utilisez-les pour informer vos décisions):"]
    for i, k in enumerate(insights, 1):
        conf_pct = int(k["confidence"] * 100)
        applied = k.get("times_applied", 0)
        lines.append(
            f"  {i}. [{k['category']}] (confiance {conf_pct}%, appliqué {applied}x) "
            f"{k['insight']}"
        )
    return "\n".join(lines)

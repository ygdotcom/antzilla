"""Knowledge page — accumulated cross-business insights."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal
from src.knowledge import store_knowledge

router = APIRouter(prefix="/knowledge")


@router.get("", response_class=HTMLResponse)
async def knowledge_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        # All insights grouped by category
        insights = (
            await db.execute(
                text(
                    "SELECT id, category, vertical, insight, data, confidence, "
                    "times_applied, times_successful, source_business_id, created_at "
                    "FROM factory_knowledge "
                    "ORDER BY confidence DESC, created_at DESC"
                )
            )
        ).fetchall()

        # Summary stats
        stats = (
            await db.execute(
                text(
                    "SELECT category, COUNT(*) AS cnt, AVG(confidence) AS avg_conf "
                    "FROM factory_knowledge GROUP BY category ORDER BY cnt DESC"
                )
            )
        ).fetchall()

        # Top 10 highest-confidence insights
        top10 = (
            await db.execute(
                text(
                    "SELECT category, insight, confidence, times_applied, times_successful "
                    "FROM factory_knowledge "
                    "ORDER BY confidence DESC LIMIT 10"
                )
            )
        ).fetchall()

    return templates.TemplateResponse("knowledge.html", {
        "request": request,
        "insights": [
            {
                "id": i.id,
                "category": i.category,
                "vertical": i.vertical,
                "insight": i.insight,
                "confidence": round(i.confidence * 100) if i.confidence else 0,
                "times_applied": i.times_applied or 0,
                "times_successful": i.times_successful or 0,
                "success_rate": round(
                    (i.times_successful or 0) / max(i.times_applied or 1, 1) * 100
                ),
                "created_at": i.created_at.isoformat() if i.created_at else "",
            }
            for i in insights
        ],
        "stats": [
            {"category": s.category, "count": s.cnt, "avg_confidence": round((s.avg_conf or 0) * 100)}
            for s in stats
        ],
        "top10": [
            {
                "category": t.category,
                "insight": t.insight,
                "confidence": round((t.confidence or 0) * 100),
                "applied": t.times_applied or 0,
                "successful": t.times_successful or 0,
            }
            for t in top10
        ],
        "total_insights": len(insights),
    })


class ManualInsight(BaseModel):
    category: str
    vertical: str = ""
    insight: str
    confidence: float = 0.7


@router.post("/add", response_class=HTMLResponse)
async def add_manual_insight(req: ManualInsight, user: str = Depends(verify_credentials)):
    """Manually add an insight (e.g. 'I talked to 3 roofers and they all said X')."""
    await store_knowledge(
        category=req.category,
        vertical=req.vertical or None,
        insight=req.insight,
        data={"source": "manual", "added_by": user},
        confidence=req.confidence,
    )
    return HTMLResponse('<span class="text-green-400">Insight added</span>')


@router.post("/{knowledge_id}/outdated", response_class=HTMLResponse)
async def mark_outdated(knowledge_id: int, user: str = Depends(verify_credentials)):
    """Mark an insight as outdated (sets confidence to 0)."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE factory_knowledge SET confidence = 0, updated_at = NOW() WHERE id = :id"),
            {"id": knowledge_id},
        )
        await db.commit()
    return HTMLResponse('<span class="text-zinc-500">Marked outdated</span>')

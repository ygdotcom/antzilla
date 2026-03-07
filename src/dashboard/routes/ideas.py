"""Idea pipeline page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.app import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/ideas")


@router.get("", response_class=HTMLResponse)
async def ideas_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        all_ideas = (await db.execute(text(
            "SELECT id, name, niche, us_equivalent, score, status, created_at "
            "FROM ideas ORDER BY score DESC NULLS LAST, created_at DESC"
        ))).fetchall()

    return templates.TemplateResponse("ideas.html", {
        "request": request,
        "ideas": [
            {"id": i.id, "name": i.name, "niche": i.niche,
             "us_equivalent": i.us_equivalent, "score": float(i.score) if i.score else None,
             "status": i.status, "at": i.created_at.isoformat() if i.created_at else ""}
            for i in all_ideas
        ],
    })


@router.get("/{idea_id}", response_class=HTMLResponse)
async def idea_detail(request: Request, idea_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        idea = (await db.execute(text(
            "SELECT id, name, niche, us_equivalent, us_equivalent_url, score, "
            "scoring_details, status, scout_report, ca_gap_analysis, created_at "
            "FROM ideas WHERE id = :id"
        ), {"id": idea_id})).fetchone()

    if not idea:
        return HTMLResponse("<h1>Idea not found</h1>", status_code=404)

    return templates.TemplateResponse("idea_detail.html", {
        "request": request,
        "idea": {
            "id": idea.id, "name": idea.name, "niche": idea.niche,
            "us_equivalent": idea.us_equivalent, "url": idea.us_equivalent_url,
            "score": float(idea.score) if idea.score else None,
            "status": idea.status, "scout_report": idea.scout_report or "",
            "gap": idea.ca_gap_analysis,
        },
    })


@router.post("/{idea_id}/advance", response_class=HTMLResponse)
async def advance_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance new → scouting."""
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'scouting' WHERE id = :id AND status = 'new'"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Advanced</span>')


@router.post("/{idea_id}/validate", response_class=HTMLResponse)
async def validate_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance scouting → validated."""
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'validated' WHERE id = :id AND status = 'scouting'"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Advanced to Validation</span>')


@router.post("/{idea_id}/archive", response_class=HTMLResponse)
async def archive_idea(idea_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'killed', kill_reason = 'Archived by CEO' WHERE id = :id"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-zinc-500">Archived</span>')

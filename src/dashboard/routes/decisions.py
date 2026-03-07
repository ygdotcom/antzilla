"""Decisions page — GO/KILL queue, pending actions, outreach approval."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/decisions")


@router.get("", response_class=HTMLResponse)
async def decisions_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        # Businesses in validation
        validating = (await db.execute(text(
            "SELECT id, name, slug, status, mrr, kill_score, created_at FROM businesses "
            "WHERE status IN ('setup','building','pre_launch') ORDER BY created_at DESC"
        ))).fetchall()

        # Kill alerts (score < 30 after 8 weeks)
        kill_alerts = (await db.execute(text(
            "SELECT id, name, slug, kill_score, created_at FROM businesses "
            "WHERE status = 'live' AND kill_score < 30 "
            "AND created_at < NOW() - INTERVAL '56 days'"
        ))).fetchall()

        # Pending human escalations from agents
        escalations = (await db.execute(text(
            "SELECT agent_name, action, result, created_at FROM agent_logs "
            "WHERE result::text LIKE '%human_needed%' OR result::text LIKE '%escalat%' "
            "ORDER BY created_at DESC LIMIT 15"
        ))).fetchall()

        # Outreach approval queue (shadow mode — pending messages)
        outreach_queue = (await db.execute(text(
            "SELECT l.id, l.name, l.email, l.company, l.score, l.business_id, "
            "b.name AS biz_name, b.slug AS biz_slug "
            "FROM leads l JOIN businesses b ON l.business_id = b.id "
            "WHERE l.status = 'contacted' "
            "AND l.last_contacted_at > NOW() - INTERVAL '24 hours' "
            "ORDER BY l.score DESC LIMIT 30"
        ))).fetchall()

        # History
        history = (await db.execute(text(
            "SELECT name, slug, status, killed_at, launched_at FROM businesses "
            "WHERE status IN ('killed','live') ORDER BY COALESCE(killed_at, launched_at) DESC LIMIT 10"
        ))).fetchall()

    return templates.TemplateResponse("decisions.html", {
        "request": request,
        "validating": [
            {"id": v.id, "name": v.name, "slug": v.slug, "status": v.status,
             "mrr": float(v.mrr or 0), "kill_score": float(v.kill_score) if v.kill_score else None,
             "age_days": (datetime.now(timezone.utc) - (v.created_at.replace(tzinfo=timezone.utc) if v.created_at and v.created_at.tzinfo is None else v.created_at)).days if v.created_at else 0}
            for v in validating
        ],
        "kill_alerts": [
            {"id": k.id, "name": k.name, "slug": k.slug, "kill_score": float(k.kill_score) if k.kill_score else 0}
            for k in kill_alerts
        ],
        "escalations": [
            {"agent": e.agent_name, "action": e.action, "at": e.created_at.isoformat()}
            for e in escalations
        ],
        "outreach_queue": [
            {"id": o.id, "name": o.name, "email": o.email, "company": o.company,
             "score": o.score or 0, "biz_name": o.biz_name, "biz_slug": o.biz_slug}
            for o in outreach_queue
        ],
        "history": [
            {"name": h.name, "slug": h.slug, "status": h.status}
            for h in history
        ],
    })

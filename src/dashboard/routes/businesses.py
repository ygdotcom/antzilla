"""Per-business deep dive + controls."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/business")


async def _get_business_data(slug: str) -> dict | None:
    async with SessionLocal() as db:
        biz = (await db.execute(text(
            "SELECT id, name, slug, domain, status, mrr, customers_count, kill_score, config, created_at "
            "FROM businesses WHERE slug = :slug"
        ), {"slug": slug})).fetchone()

        if not biz:
            return None

        # Funnel
        funnel = (await db.execute(text(
            "SELECT status, COUNT(*) AS cnt FROM leads WHERE business_id = :biz GROUP BY status"
        ), {"biz": biz.id})).fetchall()

        # Recent snapshots (30 days)
        snapshots = (await db.execute(text(
            "SELECT date, mrr, customers_active, kill_score FROM daily_snapshots "
            "WHERE business_id = :biz ORDER BY date DESC LIMIT 30"
        ), {"biz": biz.id})).fetchall()

        # Voice stats
        voice = (await db.execute(text(
            "SELECT COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
            "COUNT(*) FILTER (WHERE outcome = 'meeting_booked') AS meetings "
            "FROM voice_calls WHERE business_id = :biz AND created_at > NOW() - INTERVAL '30 days'"
        ), {"biz": biz.id})).fetchone()

        # Recent agent activity
        logs = (await db.execute(text(
            "SELECT agent_name, action, status, cost_usd, created_at FROM agent_logs "
            "WHERE business_id = :biz ORDER BY created_at DESC LIMIT 10"
        ), {"biz": biz.id})).fetchall()

        # Pending outreach (for approval queue)
        pending_outreach = (await db.execute(text(
            "SELECT id, name, email, company, score FROM leads "
            "WHERE business_id = :biz AND status = 'contacted' "
            "AND last_contacted_at > NOW() - INTERVAL '24 hours' "
            "ORDER BY score DESC LIMIT 20"
        ), {"biz": biz.id})).fetchall()

    config = json.loads(biz.config) if biz.config else {}
    return {
        "business": {
            "id": biz.id, "name": biz.name, "slug": biz.slug,
            "domain": biz.domain, "status": biz.status,
            "mrr": float(biz.mrr or 0), "customers": biz.customers_count or 0,
            "kill_score": float(biz.kill_score) if biz.kill_score else None,
        },
        "config": config,
        "budget_daily": config.get("budget_daily", 10),
        "email_volume": config.get("email_volume", 50),
        "voice_volume": config.get("voice_volume", 10),
        "paused": config.get("paused", False),
        "funnel": {r.status: r.cnt for r in funnel},
        "snapshots": [
            {"date": s.date.isoformat(), "mrr": float(s.mrr or 0),
             "customers": s.customers_active or 0, "kill_score": float(s.kill_score) if s.kill_score else None}
            for s in snapshots
        ],
        "voice": {
            "total": voice.total or 0,
            "completed": voice.completed or 0,
            "meetings": voice.meetings or 0,
            "connect_rate": round(voice.completed / max(voice.total, 1) * 100, 1),
        },
        "logs": [
            {"agent": l.agent_name, "action": l.action, "status": l.status,
             "cost": float(l.cost_usd or 0), "at": l.created_at.isoformat()}
            for l in logs
        ],
        "pending_outreach": [
            {"id": p.id, "name": p.name, "email": p.email, "company": p.company, "score": p.score or 0}
            for p in pending_outreach
        ],
    }


@router.get("/{slug}", response_class=HTMLResponse)
async def business_detail(request: Request, slug: str, user: str = Depends(verify_credentials)):
    data = await _get_business_data(slug)
    if not data:
        return HTMLResponse("<h1>Business not found</h1>", status_code=404)
    return templates.TemplateResponse("business.html", {"request": request, **data})


@router.post("/{slug}/controls", response_class=HTMLResponse)
async def update_controls(
    request: Request,
    slug: str,
    budget_daily: float = Form(10),
    email_volume: int = Form(50),
    voice_volume: int = Form(10),
    paused: bool = Form(False),
    user: str = Depends(verify_credentials),
):
    """HTMX endpoint — update business controls (budget, volume, pause)."""
    async with SessionLocal() as db:
        biz = (await db.execute(text("SELECT id, config FROM businesses WHERE slug = :slug"), {"slug": slug})).fetchone()
        if not biz:
            return HTMLResponse("Not found", status_code=404)

        config = json.loads(biz.config) if biz.config else {}
        config["budget_daily"] = budget_daily
        config["email_volume"] = email_volume
        config["voice_volume"] = voice_volume
        config["paused"] = paused

        await db.execute(text(
            "UPDATE businesses SET config = :config, updated_at = NOW() WHERE id = :id"
        ), {"config": json.dumps(config), "id": biz.id})
        await db.commit()

    return HTMLResponse('<div class="text-green-400 text-sm">Settings saved</div>')


@router.post("/{slug}/kill", response_class=HTMLResponse)
async def kill_business(request: Request, slug: str, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE businesses SET status = 'killed', killed_at = NOW(), updated_at = NOW() WHERE slug = :slug"
        ), {"slug": slug})
        await db.execute(text(
            "INSERT INTO agent_logs (agent_name, action, result, status) "
            "VALUES ('ceo_dashboard', :action, :result, 'success')"
        ), {"action": f"business_killed: {slug}", "result": json.dumps({"slug": slug})})
        await db.commit()
    return RedirectResponse("/decisions", status_code=303)


@router.post("/{slug}/advance", response_class=HTMLResponse)
async def advance_business(request: Request, slug: str, user: str = Depends(verify_credentials)):
    """Advance business to next stage: setup→building, building→pre_launch, pre_launch→live."""
    async with SessionLocal() as db:
        biz = (await db.execute(text("SELECT id, status FROM businesses WHERE slug = :slug"), {"slug": slug})).fetchone()
        if not biz:
            return HTMLResponse("Not found", status_code=404)
        next_status = {"setup": "building", "building": "pre_launch", "pre_launch": "live"}.get(biz.status)
        if not next_status:
            return HTMLResponse('<span class="text-zinc-500">Already at final stage</span>')
        await db.execute(text(
            "UPDATE businesses SET status = :status, launched_at = CASE WHEN :status = 'live' THEN NOW() ELSE launched_at END, updated_at = NOW() WHERE slug = :slug"
        ), {"status": next_status, "slug": slug})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Advanced</span>')


@router.post("/{slug}/double-down", response_class=HTMLResponse)
async def double_down(request: Request, slug: str, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        biz = (await db.execute(text("SELECT id, config FROM businesses WHERE slug = :slug"), {"slug": slug})).fetchone()
        if biz:
            config = json.loads(biz.config) if biz.config else {}
            config["budget_daily"] = config.get("budget_daily", 10) * 2
            await db.execute(text(
                "UPDATE businesses SET config = :config, updated_at = NOW() WHERE id = :id"
            ), {"config": json.dumps(config), "id": biz.id})
            await db.commit()
    return RedirectResponse(f"/business/{slug}", status_code=303)

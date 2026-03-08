"""Budget & costs page."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from src.config import settings
from src.crypto import encrypt
from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/budget")


@router.get("", response_class=HTMLResponse)
async def budget_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        daily = (await db.execute(text(
            "SELECT date, api_provider, SUM(cost_usd) AS cost "
            "FROM budget_tracking WHERE date > CURRENT_DATE - 7 "
            "GROUP BY date, api_provider ORDER BY date DESC"
        ))).fetchall()

        agent_costs = (await db.execute(text(
            "SELECT agent_name, SUM(cost_usd) AS total "
            "FROM agent_logs WHERE created_at > DATE_TRUNC('month', CURRENT_DATE) "
            "GROUP BY agent_name ORDER BY total DESC"
        ))).fetchall()

        biz_alloc = (await db.execute(text(
            "SELECT slug, name, config FROM businesses WHERE status IN ('live','pre_launch','building')"
        ))).fetchall()

        today = (await db.execute(text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM agent_logs WHERE created_at > CURRENT_DATE"
        ))).fetchone()

        month = (await db.execute(text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM agent_logs WHERE created_at > DATE_TRUNC('month', CURRENT_DATE)"
        ))).fetchone()

    allocations = []
    for b in biz_alloc:
        cfg = json.loads(b.config) if b.config else {}
        allocations.append({"slug": b.slug, "name": b.name, "budget": cfg.get("budget_daily", 10)})

    return templates.TemplateResponse("budget.html", {
        "request": request,
        "spend_today": float(today.total),
        "spend_month": float(month.total),
        "budget_daily_limit": settings.DAILY_BUDGET_LIMIT_USD,
        "daily_costs": [
            {"date": d.date.isoformat(), "provider": d.api_provider, "cost": float(d.cost)}
            for d in daily
        ],
        "agent_costs": [
            {"agent": a.agent_name, "cost": float(a.total)}
            for a in agent_costs
        ],
        "allocations": allocations,
    })


@router.post("/throttle-all", response_class=HTMLResponse)
async def throttle_all(user: str = Depends(verify_credentials)):
    """Emergency: throttle all agents to Haiku. Persists via secrets table."""
    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO secrets (key, value_encrypted, category, display_name, is_configured, updated_at) "
                "VALUES ('MODEL_OVERRIDE', :val, 'core', 'Model Override', TRUE, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value_encrypted = EXCLUDED.value_encrypted, "
                "is_configured = TRUE, updated_at = NOW()"
            ),
            {"val": encrypt("haiku")},
        )
        await db.commit()
    settings.invalidate("MODEL_OVERRIDE")
    return HTMLResponse('<span class="text-yellow-400 text-sm font-medium">All agents throttled to Haiku</span>')


@router.post("/pause-nonessential", response_class=HTMLResponse)
async def pause_nonessential(user: str = Depends(verify_credentials)):
    """Emergency: pause non-essential agents. Persists via secrets table."""
    paused = json.dumps(["content_engine", "social_agent", "competitor_watch", "growth_hacker", "self_reflection"])
    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO secrets (key, value_encrypted, category, display_name, is_configured, updated_at) "
                "VALUES ('PAUSED_AGENTS', :val, 'core', 'Paused Agents', TRUE, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value_encrypted = EXCLUDED.value_encrypted, "
                "is_configured = TRUE, updated_at = NOW()"
            ),
            {"val": encrypt(paused)},
        )
        await db.commit()
    settings.invalidate("PAUSED_AGENTS")
    return HTMLResponse('<span class="text-red-400 text-sm font-medium">Non-essential agents paused</span>')


class AllocationSave(BaseModel):
    slug: str
    budget: float


@router.post("/allocations", response_class=HTMLResponse)
async def save_allocation(req: AllocationSave, user: str = Depends(verify_credentials)):
    """Save per-business budget allocation."""
    async with SessionLocal() as db:
        biz = (await db.execute(
            text("SELECT id, config FROM businesses WHERE slug = :slug"), {"slug": req.slug}
        )).fetchone()
        if not biz:
            return HTMLResponse('<span class="text-red-400 text-sm">Business not found</span>')
        cfg = json.loads(biz.config) if biz.config else {}
        cfg["budget_daily"] = req.budget
        await db.execute(
            text("UPDATE businesses SET config = :cfg, updated_at = NOW() WHERE id = :id"),
            {"cfg": json.dumps(cfg), "id": biz.id},
        )
        await db.commit()
    return HTMLResponse(f'<span class="text-brand text-sm">Saved ${req.budget}/day</span>')

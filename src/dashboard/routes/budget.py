"""Budget & costs page."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.app import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/budget")


@router.get("", response_class=HTMLResponse)
async def budget_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        # Daily costs by provider (last 7 days)
        daily = (await db.execute(text(
            "SELECT date, api_provider, SUM(cost_usd) AS cost "
            "FROM budget_tracking WHERE date > CURRENT_DATE - 7 "
            "GROUP BY date, api_provider ORDER BY date DESC"
        ))).fetchall()

        # Per-agent monthly cost
        agent_costs = (await db.execute(text(
            "SELECT agent_name, SUM(cost_usd) AS total "
            "FROM agent_logs WHERE created_at > DATE_TRUNC('month', CURRENT_DATE) "
            "GROUP BY agent_name ORDER BY total DESC"
        ))).fetchall()

        # Per-business allocation
        biz_alloc = (await db.execute(text(
            "SELECT slug, name, config FROM businesses WHERE status IN ('live','pre_launch','building')"
        ))).fetchall()

        # Today's total
        today = (await db.execute(text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM agent_logs WHERE created_at > CURRENT_DATE"
        ))).fetchone()

        # Month total
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
        "budget_daily_limit": 50.0,
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
    """Emergency: throttle all agents to Haiku."""
    return HTMLResponse('<div class="text-yellow-400">All agents throttled to Haiku tier</div>')


@router.post("/pause-nonessential", response_class=HTMLResponse)
async def pause_nonessential(user: str = Depends(verify_credentials)):
    """Emergency: pause all non-essential agents."""
    return HTMLResponse('<div class="text-red-400">Non-essential agents paused</div>')

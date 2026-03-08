"""Overview page — factory-wide metrics at a glance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.config import settings
from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter()


async def _get_overview_data() -> dict:
    async with SessionLocal() as db:
        # Total MRR
        mrr = (await db.execute(text("SELECT COALESCE(SUM(mrr), 0) AS total FROM businesses WHERE status = 'live'"))).fetchone()

        # Customer counts
        custs = (await db.execute(text(
            "SELECT COUNT(*) FILTER (WHERE status = 'active') AS active, "
            "COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS new_7d, "
            "COUNT(*) FILTER (WHERE status = 'churned' AND created_at > NOW() - INTERVAL '7 days') AS churned_7d "
            "FROM customers"
        ))).fetchone()

        # Leads in pipeline
        leads = (await db.execute(text("SELECT COUNT(*) AS total FROM leads WHERE status NOT IN ('converted','lost','unsubscribed')"))).fetchone()

        # API spend today
        spend_today = (await db.execute(text("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM agent_logs WHERE created_at > CURRENT_DATE"))).fetchone()
        spend_month = (await db.execute(text("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM agent_logs WHERE created_at > DATE_TRUNC('month', CURRENT_DATE)"))).fetchone()

        # Agent activity today
        agents_today = (await db.execute(text(
            "SELECT COUNT(*) AS runs, "
            "COUNT(*) FILTER (WHERE status = 'success') AS successes, "
            "COUNT(*) FILTER (WHERE status = 'error') AS errors "
            "FROM agent_logs WHERE created_at > CURRENT_DATE"
        ))).fetchone()

        # Businesses
        biz_list = (await db.execute(text(
            "SELECT id, name, slug, status, mrr, customers_count, kill_score FROM businesses ORDER BY mrr DESC"
        ))).fetchall()

        # Top improvements
        improvements = (await db.execute(text(
            "SELECT target_agent, description, priority FROM improvements WHERE status = 'proposed' ORDER BY impact_score DESC NULLS LAST LIMIT 3"
        ))).fetchall()

    return {
        "total_mrr": float(mrr.total),
        "customers_active": custs.active or 0,
        "customers_new_7d": custs.new_7d or 0,
        "customers_churned_7d": custs.churned_7d or 0,
        "leads_pipeline": leads.total or 0,
        "spend_today": float(spend_today.total),
        "spend_month": float(spend_month.total),
        "budget_daily": 50.0,
        "agent_runs_today": agents_today.runs or 0,
        "agent_success_rate": round(agents_today.successes / max(agents_today.runs, 1) * 100, 1),
        "agent_errors_today": agents_today.errors or 0,
        "businesses": [
            {"id": b.id, "name": b.name, "slug": b.slug, "status": b.status,
             "mrr": float(b.mrr or 0), "customers": b.customers_count or 0,
             "kill_score": float(b.kill_score) if b.kill_score else None}
            for b in biz_list
        ],
        "improvements": [
            {"agent": i.target_agent, "description": i.description, "priority": i.priority}
            for i in improvements
        ],
    }


@router.get("/", response_class=HTMLResponse)
async def overview(request: Request, user: str = Depends(verify_credentials)):
    data = await _get_overview_data()
    data["setup_needed"] = not settings.is_setup_complete()
    return templates.TemplateResponse("overview.html", {"request": request, **data})

"""Agent performance page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.app import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/agents")


@router.get("", response_class=HTMLResponse)
async def agent_list(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        agents = (await db.execute(text(
            "SELECT agent_name, "
            "COUNT(*) AS total_runs, "
            "COUNT(*) FILTER (WHERE status = 'success') AS successes, "
            "COUNT(*) FILTER (WHERE status = 'error') AS errors, "
            "COALESCE(SUM(cost_usd), 0) AS total_cost, "
            "MAX(created_at) AS last_run "
            "FROM agent_logs "
            "WHERE created_at > NOW() - INTERVAL '7 days' "
            "GROUP BY agent_name ORDER BY total_runs DESC"
        ))).fetchall()

        errors = (await db.execute(text(
            "SELECT agent_name, action, error_message, created_at FROM agent_logs "
            "WHERE status = 'error' AND created_at > NOW() - INTERVAL '7 days' "
            "ORDER BY created_at DESC LIMIT 20"
        ))).fetchall()

        proposals = (await db.execute(text(
            "SELECT id, target_agent, category, description, priority, status, impact_score "
            "FROM improvements ORDER BY impact_score DESC NULLS LAST LIMIT 20"
        ))).fetchall()

    return templates.TemplateResponse("agents.html", {
        "request": request,
        "agents": [
            {"name": a.agent_name, "runs": a.total_runs,
             "success_rate": round(a.successes / max(a.total_runs, 1) * 100, 1),
             "errors": a.errors, "cost": float(a.total_cost),
             "last_run": a.last_run.isoformat() if a.last_run else "never"}
            for a in agents
        ],
        "errors": [
            {"agent": e.agent_name, "action": e.action, "error": e.error_message,
             "at": e.created_at.isoformat()}
            for e in errors
        ],
        "proposals": [
            {"id": p.id, "agent": p.target_agent, "category": p.category,
             "description": p.description, "priority": p.priority,
             "status": p.status, "impact": float(p.impact_score) if p.impact_score else None}
            for p in proposals
        ],
    })


@router.post("/proposals/{proposal_id}/approve", response_class=HTMLResponse)
async def approve_proposal(proposal_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE improvements SET status = 'approved' WHERE id = :id"), {"id": proposal_id})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Approved</span>')


@router.post("/proposals/{proposal_id}/reject", response_class=HTMLResponse)
async def reject_proposal(proposal_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE improvements SET status = 'rejected' WHERE id = :id"), {"id": proposal_id})
        await db.commit()
    return HTMLResponse('<span class="text-red-400">Rejected</span>')

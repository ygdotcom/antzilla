"""Live console — real-time view of factory activity."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/console")


@router.get("", response_class=HTMLResponse)
async def console_page(request: Request, user: str = Depends(verify_credentials)):
    return templates.TemplateResponse("console.html", {"request": request})


@router.get("/feed", response_class=HTMLResponse)
async def console_feed(request: Request, user: str = Depends(verify_credentials)):
    """Returns the latest 50 agent log entries as HTML rows. Polled by HTMX."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT agent_name, action, status, cost_usd, duration_seconds, "
                    "error_message, business_id, created_at "
                    "FROM agent_logs ORDER BY created_at DESC LIMIT 50"
                )
            )
        ).fetchall()

        triggers = (
            await db.execute(
                text(
                    "SELECT workflow_name, status, triggered_by, created_at "
                    "FROM workflow_triggers ORDER BY created_at DESC LIMIT 10"
                )
            )
        ).fetchall()

    html_parts = []

    for t in triggers:
        status_color = "text-yellow-400" if t.status == "pending" else "text-brand" if t.status == "completed" else "text-zinc-400"
        html_parts.append(
            f'<div class="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 text-sm">'
            f'<span class="text-zinc-500 text-xs w-44 shrink-0">{t.created_at.strftime("%H:%M:%S") if t.created_at else ""}</span>'
            f'<span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/20 text-violet-400 border border-violet-500/30">trigger</span>'
            f'<span class="text-white font-medium">{t.workflow_name}</span>'
            f'<span class="{status_color}">{t.status}</span>'
            f'<span class="text-zinc-500 ml-auto">by {t.triggered_by or "system"}</span>'
            f'</div>'
        )

    for r in rows:
        if r.status == "success":
            status_badge = '<span class="px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">ok</span>'
        elif r.status == "error":
            status_badge = '<span class="px-2 py-0.5 rounded text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30">err</span>'
        else:
            status_badge = f'<span class="px-2 py-0.5 rounded text-xs font-medium bg-zinc-700 text-zinc-400">{r.status}</span>'

        cost = f"${r.cost_usd:.4f}" if r.cost_usd else ""
        duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else ""
        error = f'<span class="text-red-400 text-xs ml-2">{r.error_message[:80]}</span>' if r.error_message else ""
        ts = r.created_at.strftime("%H:%M:%S") if r.created_at else ""

        html_parts.append(
            f'<div class="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 text-sm hover:bg-zinc-800/30">'
            f'<span class="text-zinc-500 text-xs w-44 shrink-0">{ts}</span>'
            f'{status_badge}'
            f'<span class="text-zinc-300 font-mono text-xs">{r.agent_name}</span>'
            f'<span class="text-zinc-400">{r.action}</span>'
            f'<span class="text-zinc-500 text-xs">{duration}</span>'
            f'<span class="text-zinc-500 text-xs">{cost}</span>'
            f'{error}'
            f'</div>'
        )

    if not html_parts:
        html_parts.append(
            '<div class="px-4 py-8 text-center text-zinc-500">'
            'No activity yet. Agents will appear here when they run.'
            '</div>'
        )

    return HTMLResponse("\n".join(html_parts))

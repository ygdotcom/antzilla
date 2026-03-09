"""Live console — real-time unified view of all factory activity."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/console")


@router.get("", response_class=HTMLResponse)
async def console_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        agents = (await db.execute(text(
            "SELECT DISTINCT agent_name FROM agent_logs ORDER BY agent_name"
        ))).fetchall()
        businesses = (await db.execute(text(
            "SELECT id, name FROM businesses ORDER BY id"
        ))).fetchall()

    return templates.TemplateResponse("console.html", {
        "request": request,
        "agents": [a.agent_name for a in agents],
        "businesses": [{"id": b.id, "name": b.name} for b in businesses],
    })


@router.get("/feed", response_class=HTMLResponse)
async def console_feed(
    request: Request,
    user: str = Depends(verify_credentials),
    agent: str = "",
    business_id: str = "",
):
    """Returns all events merged and sorted by time. Polled by HTMX."""
    conditions = []
    params: dict = {}

    if agent:
        conditions.append("agent_name = :agent")
        params["agent"] = agent
    if business_id:
        conditions.append("business_id = :biz")
        params["biz"] = int(business_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with SessionLocal() as db:
        # Agent logs — the main source of events
        rows = (await db.execute(text(
            f"SELECT id, agent_name, action, status, cost_usd, result::text, "
            f"error_message, business_id, created_at "
            f"FROM agent_logs {where} ORDER BY created_at DESC LIMIT 100"
        ), params)).fetchall()

        # Workflow triggers
        trigger_rows = (await db.execute(text(
            "SELECT workflow_name, status, triggered_by, created_at "
            "FROM workflow_triggers ORDER BY created_at DESC LIMIT 20"
        ))).fetchall()

        # Business name lookup
        biz_names = {}
        biz_rows = (await db.execute(text("SELECT id, name FROM businesses"))).fetchall()
        for b in biz_rows:
            biz_names[b.id] = b.name

    # Merge all events into one sorted list
    events = []

    for r in rows:
        # Parse result JSON for details
        detail = ""
        if r.result:
            try:
                res = json.loads(r.result) if isinstance(r.result, str) else r.result
                detail = _format_result(res, r.action)
            except (json.JSONDecodeError, TypeError):
                detail = str(r.result)[:100] if r.result else ""

        events.append({
            "type": "log",
            "ts": r.created_at,
            "agent": r.agent_name,
            "action": r.action,
            "status": r.status,
            "cost": float(r.cost_usd) if r.cost_usd else 0,
            "error": r.error_message or "",
            "business": biz_names.get(r.business_id, ""),
            "business_id": r.business_id,
            "detail": detail,
            "id": r.id,
        })

    for t in trigger_rows:
        events.append({
            "type": "trigger",
            "ts": t.created_at,
            "agent": t.workflow_name,
            "action": t.status,
            "status": t.status,
            "cost": 0,
            "error": "",
            "business": "",
            "business_id": None,
            "detail": f"by {t.triggered_by or 'system'}",
            "id": 0,
        })

    # Sort ALL events by timestamp descending
    events.sort(key=lambda e: e["ts"] or "", reverse=True)

    # Render HTML
    html_parts = []
    for e in events[:100]:
        ts = e["ts"].strftime("%b %d %H:%M:%S") if e["ts"] else ""

        if e["type"] == "trigger":
            status_color = {"pending": "text-yellow-400", "running": "text-blue-400",
                            "completed": "text-brand", "failed": "text-red-400"}.get(e["status"], "text-zinc-400")
            html_parts.append(
                f'<div class="flex items-start gap-3 px-4 py-2.5 border-b border-zinc-800/50 text-sm">'
                f'<span class="text-zinc-600 text-xs w-32 shrink-0 pt-0.5">{ts}</span>'
                f'<span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/20 text-violet-400 border border-violet-500/30">trigger</span>'
                f'<span class="text-white font-medium">{e["agent"]}</span>'
                f'<span class="{status_color} text-xs">{e["status"]}</span>'
                f'<span class="text-zinc-600 text-xs ml-auto">{e["detail"]}</span>'
                f'</div>'
            )
        else:
            # Status badge
            if e["status"] == "success":
                badge = '<span class="w-5 h-5 flex items-center justify-center rounded-full bg-green-500/20 text-green-400 text-xs">&#10003;</span>'
            elif e["status"] == "error":
                badge = '<span class="w-5 h-5 flex items-center justify-center rounded-full bg-red-500/20 text-red-400 text-xs">&#10007;</span>'
            else:
                badge = f'<span class="w-5 h-5 flex items-center justify-center rounded-full bg-zinc-700 text-zinc-400 text-xs">&#8226;</span>'

            cost_str = f'<span class="text-zinc-600 text-xs">${e["cost"]:.4f}</span>' if e["cost"] else ""
            biz_tag = f'<span class="px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400 border border-zinc-700">{e["business"]}</span>' if e["business"] else ""
            error_str = f'<div class="text-red-400/80 text-xs mt-1 pl-8">{e["error"][:150]}</div>' if e["error"] else ""
            detail_str = f'<div class="text-zinc-500 text-xs mt-1 pl-8">{e["detail"]}</div>' if e["detail"] else ""

            html_parts.append(
                f'<div class="px-4 py-2.5 border-b border-zinc-800/50 text-sm hover:bg-zinc-800/20 transition-colors">'
                f'<div class="flex items-center gap-3">'
                f'<span class="text-zinc-600 text-xs w-32 shrink-0">{ts}</span>'
                f'{badge}'
                f'<span class="text-zinc-300 font-mono text-xs">{e["agent"]}</span>'
                f'<span class="text-zinc-400 flex-1 truncate">{e["action"]}</span>'
                f'{biz_tag}'
                f'{cost_str}'
                f'</div>'
                f'{detail_str}'
                f'{error_str}'
                f'</div>'
            )

    if not html_parts:
        html_parts.append(
            '<div class="px-4 py-12 text-center text-zinc-500">'
            'No activity yet. Agents will appear here when they run.'
            '</div>'
        )

    return HTMLResponse("\n".join(html_parts))


def _format_result(res: dict, action: str) -> str:
    """Extract the most useful info from a result dict."""
    if not isinstance(res, dict):
        return ""

    parts = []

    # Common patterns
    if "saved" in res:
        parts.append(f"saved {res['saved']}")
    if "top_3" in res and res["top_3"]:
        names = [i.get("name", "") for i in res["top_3"][:3]]
        parts.append(f"top: {', '.join(names)}")
    if "go_nogo" in res:
        parts.append(f"{'GO' if res['go_nogo'] == 'go' else 'NO-GO'}")
    if "idea_id" in res:
        parts.append(f"idea #{res['idea_id']}")
    if "business_id" in res and res["business_id"]:
        parts.append(f"biz #{res['business_id']}")
    if "github_repo" in res and res["github_repo"]:
        parts.append(f"repo: {res['github_repo']}")
    if "deployment_url" in res and res["deployment_url"]:
        url = res["deployment_url"]
        parts.append(f'<a href="https://{url}" target="_blank" class="text-brand hover:underline">{url[:40]}</a>')
    if "files_pushed" in res:
        parts.append(f"{res['files_pushed']} files")
    if "files" in res and isinstance(res["files"], int):
        parts.append(f"{res['files']} files")
    if "pushed" in res and isinstance(res["pushed"], int):
        parts.append(f"pushed {res['pushed']}")
    if "overall_score" in res:
        parts.append(f"design: {res['overall_score']}/10")
    if "supabase" in res and isinstance(res["supabase"], bool):
        parts.append(f"supabase: {'ok' if res['supabase'] else 'skip'}")
    if "stripe" in res and isinstance(res["stripe"], bool):
        parts.append(f"stripe: {'ok' if res['stripe'] else 'skip'}")
    if "set" in res and "total" in res:
        parts.append(f"env vars: {res['set']}/{res['total']}")
    if "from" in res and "to" in res:
        parts.append(f"{res['from']} → {res['to']}")
    if "error" in res and res["error"]:
        parts.append(f"err: {str(res['error'])[:80]}")
    if "summary" in res and res["summary"]:
        parts.append(res["summary"][:80])
    if "down_count" in res and res["down_count"]:
        down = [r["name"] for r in res.get("results", []) if r.get("status") == "down"]
        parts.append(f"down: {', '.join(down)}")
    if "recommended_name" in res:
        parts.append(f"name: {res['recommended_name']}")

    return " · ".join(parts) if parts else ""

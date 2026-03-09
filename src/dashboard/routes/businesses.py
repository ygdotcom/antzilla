"""Per-business deep dive + controls."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/business")


def _parse_config(val) -> dict:
    """Safely parse config — handles both JSONB (dict) and TEXT (str)."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


async def _get_business_data(slug: str) -> dict | None:
    async with SessionLocal() as db:
        biz = (await db.execute(text(
            "SELECT id, name, slug, domain, status, mrr, customers_count, kill_score, config, "
            "github_repo, vercel_project_id, created_at "
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

    config = _parse_config(biz.config)
    return {
        "business": {
            "id": biz.id, "name": biz.name, "slug": biz.slug,
            "domain": biz.domain, "status": biz.status,
            "github_repo": getattr(biz, "github_repo", None),
            "vercel_project_id": getattr(biz, "vercel_project_id", None),
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

        config = _parse_config(biz.config)
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
            config = _parse_config(biz.config)
            config["budget_daily"] = config.get("budget_daily", 10) * 2
            await db.execute(text(
                "UPDATE businesses SET config = :config, updated_at = NOW() WHERE id = :id"
            ), {"config": json.dumps(config), "id": biz.id})
            await db.commit()
    return RedirectResponse(f"/business/{slug}", status_code=303)


@router.post("/{slug}/rebuild", response_class=HTMLResponse)
async def rebuild_business(request: Request, slug: str, user: str = Depends(verify_credentials)):
    """Reset business and re-trigger the build pipeline."""
    async with SessionLocal() as db:
        biz = (await db.execute(text(
            "SELECT id, idea_id FROM businesses WHERE slug = :slug"
        ), {"slug": slug})).fetchone()
        if not biz:
            return HTMLResponse("Not found", status_code=404)

        # Clean up old GitHub repo and Vercel project
        try:
            from src.config import settings
            import httpx as _httpx
            gh = settings.get("GITHUB_TOKEN")
            vc = settings.get("VERCEL_TOKEN")
            old_repo = (await db.execute(text("SELECT github_repo FROM businesses WHERE id = :id"), {"id": biz.id})).fetchone()
            async with _httpx.AsyncClient(timeout=10) as c:
                if old_repo and old_repo.github_repo:
                    await c.delete(f"https://api.github.com/repos/{old_repo.github_repo}",
                                   headers={"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json"})
                await c.delete(f"https://api.vercel.com/v9/projects/{slug}",
                               headers={"Authorization": f"Bearer {vc}"})
        except Exception:
            pass

        await db.execute(text(
            "UPDATE businesses SET status = 'setup', github_repo = NULL, domain = NULL, "
            "vercel_project_id = NULL, supabase_url = NULL, supabase_anon_key = NULL, "
            "updated_at = NOW() WHERE id = :id"
        ), {"id": biz.id})
        await db.execute(text(
            "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
            "VALUES ('ceo_dashboard', 'rebuild_triggered', :result, 'success', :biz_id)"
        ), {"result": json.dumps({"slug": slug}), "biz_id": biz.id})
        await db.commit()

        # Trigger the build pipeline
        from src.dashboard.app import run_build_pipeline
        await run_build_pipeline(biz.id)

    return HTMLResponse(
        '<span class="text-brand animate-pulse">Rebuilding... check Console</span>'
    )


@router.post("/{slug}/prompt", response_class=HTMLResponse)
async def vibe_code(request: Request, slug: str, user: str = Depends(verify_credentials)):
    """Send a prompt to v0 to modify/improve the business app."""
    from src.config import settings

    form = await request.form()
    prompt = form.get("prompt", "").strip()
    if not prompt:
        return HTMLResponse('<div class="text-red-400 text-sm">Enter a prompt</div>')

    v0_key = settings.get("V0_API_KEY")
    if not v0_key:
        return HTMLResponse('<div class="text-red-400 text-sm">V0_API_KEY not configured in Settings</div>')

    async with SessionLocal() as db:
        biz = (await db.execute(text(
            "SELECT id, config FROM businesses WHERE slug = :slug"
        ), {"slug": slug})).fetchone()
        if not biz:
            return HTMLResponse("Not found", status_code=404)

    config = _parse_config(biz.config)
    chat_id = config.get("v0_chat_id", "")

    if not chat_id:
        return HTMLResponse(
            '<div class="text-yellow-400 text-sm">No v0 chat found for this business. '
            'Rebuild with V0_API_KEY configured to enable vibe-coding.</div>'
        )

    try:
        from src.integrations.v0_client import send_message, get_chat
        result = await send_message(chat_id, prompt)

        # Get updated demo URL
        chat_data = await get_chat(chat_id)
        demo_url = chat_data.get("demo", "")

        # Log the action
        async with SessionLocal() as db:
            await db.execute(text(
                "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                "VALUES ('ceo_dashboard', 'vibe_code', :result, 'success', :biz_id)"
            ), {
                "result": json.dumps({"prompt": prompt[:200], "chat_id": chat_id}),
                "biz_id": biz.id,
            })
            if demo_url:
                await db.execute(text(
                    "UPDATE businesses SET domain = :domain, updated_at = NOW() WHERE id = :id"
                ), {"domain": demo_url, "id": biz.id})
            await db.commit()

        return HTMLResponse(
            f'<div class="space-y-2">'
            f'<div class="text-brand text-sm">Sent to v0. Changes deploying...</div>'
            f'{f"""<a href="https://{demo_url}" target="_blank" class="text-brand text-xs hover:underline">Preview → {demo_url[:50]}</a>""" if demo_url else ""}'
            f'</div>'
        )

    except Exception as exc:
        return HTMLResponse(f'<div class="text-red-400 text-sm">Error: {exc}</div>')

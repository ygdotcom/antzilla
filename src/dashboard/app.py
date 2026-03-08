"""CEO Dashboard — FastAPI + HTMX + Tailwind.

Auth via Supabase (email/password). Session stored in HMAC-signed cookie.
First boot: /login → /setup wizard if no secrets configured.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.dashboard.deps import (
    SESSION_COOKIE,
    _sign_token,
    check_password,
    get_current_user,
    templates,
    verify_credentials,
)

logger = structlog.get_logger()

app = FastAPI(title="Factory Dashboard", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect to /login if not authenticated."""

    async def dispatch(self, request, call_next):
        path = request.url.path

        if path.startswith(("/login", "/static")):
            return await call_next(request)

        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)

        return await call_next(request)


app.add_middleware(AuthMiddleware)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user_info = check_password(username, password)
    if user_info:
        token = _sign_token(user_info["username"], user_info.get("role", "admin"))
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=86400 * 7)
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid email or password."},
        status_code=401,
    )


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


from src.dashboard.routes import overview, businesses, agents, budget, console, decisions, ideas, knowledge, leads, secrets_api

app.include_router(overview.router)
app.include_router(businesses.router)
app.include_router(agents.router)
app.include_router(budget.router)
app.include_router(console.router)
app.include_router(decisions.router)
app.include_router(ideas.router)
app.include_router(knowledge.router)
app.include_router(leads.router)
app.include_router(secrets_api.router)


AGENT_RUNNERS = {
    "idea-factory": ("src.agents.idea_factory", "IdeaFactory", [
        "scrape_sources", "filter_canadian_gap", "score_ideas", "filter_complexity", "save_and_notify"
    ]),
    "self-reflection": ("src.agents.self_reflection", "SelfReflectionAgent", [
        "gather_data", "analyze", "categorize_findings", "save_improvements", "send_report"
    ]),
}


@app.post("/trigger/{workflow_name}", response_class=HTMLResponse)
async def trigger_workflow(request: Request, workflow_name: str, user: str = Depends(verify_credentials)):
    """Run an agent directly — no Hatchet, no queue, instant execution."""
    import asyncio
    import importlib
    from sqlalchemy import text as sa_text
    from src.db import SessionLocal
    current = get_current_user(request)
    triggered_by = current.get("username", "unknown") if current else "unknown"

    runner = AGENT_RUNNERS.get(workflow_name)
    if not runner:
        return HTMLResponse(
            f'<span class="text-yellow-400 text-sm">No instant runner for {workflow_name} — runs on schedule</span>'
        )

    module_path, class_name, steps = runner

    # Log the trigger
    async with SessionLocal() as db:
        await db.execute(
            sa_text(
                "INSERT INTO workflow_triggers (workflow_name, status, triggered_by) "
                "VALUES (:wf, 'running', :user)"
            ),
            {"wf": workflow_name, "user": triggered_by},
        )
        await db.commit()

    # Run agent in background so the button responds immediately
    async def _run_agent():
        try:
            mod = importlib.import_module(module_path)
            agent_class = getattr(mod, class_name)
            agent = agent_class()

            class FakeContext:
                def __init__(self):
                    self._outputs = {}
                def step_output(self, name):
                    return self._outputs.get(name, {})
                def workflow_input(self):
                    return {}

            ctx = FakeContext()
            for step_name in steps:
                logger.info("agent_step_starting", agent=workflow_name, step=step_name)
                try:
                    method = getattr(agent, step_name)
                    result = await method(ctx)
                    ctx._outputs[step_name] = result if isinstance(result, dict) else {}
                    logger.info("agent_step_complete", agent=workflow_name, step=step_name, result_keys=list(result.keys()) if isinstance(result, dict) else [])
                except Exception as step_exc:
                    logger.error("agent_step_failed", agent=workflow_name, step=step_name, error=str(step_exc))
                    raise

            async with SessionLocal() as db:
                await db.execute(
                    sa_text(
                        "UPDATE workflow_triggers SET status = 'completed', completed_at = NOW() "
                        "WHERE id = (SELECT id FROM workflow_triggers WHERE workflow_name = :wf AND status = 'running' ORDER BY created_at DESC LIMIT 1)"
                    ),
                    {"wf": workflow_name},
                )
                await db.commit()
            logger.info("agent_run_complete", agent=workflow_name)
        except Exception as exc:
            logger.error("agent_run_failed", agent=workflow_name, error=str(exc), error_type=type(exc).__name__)
            try:
                async with SessionLocal() as db:
                    await db.execute(
                        sa_text(
                            "UPDATE workflow_triggers SET status = 'failed', completed_at = NOW() "
                            "WHERE id = (SELECT id FROM workflow_triggers WHERE workflow_name = :wf AND status = 'running' ORDER BY created_at DESC LIMIT 1)"
                        ),
                        {"wf": workflow_name},
                    )
                    await db.commit()
            except Exception:
                pass

    asyncio.create_task(_run_agent())

    return HTMLResponse(
        f'<span class="text-brand text-sm font-medium animate-pulse">Running {workflow_name}... check Console</span>'
    )


@app.get("/businesses", response_class=HTMLResponse)
async def businesses_list(request: Request, user: str = Depends(verify_credentials)):
    from sqlalchemy import text as sa_text
    from src.db import SessionLocal
    async with SessionLocal() as db:
        rows = (await db.execute(sa_text(
            "SELECT id, name, slug, status, mrr, customers_count, kill_score, domain "
            "FROM businesses ORDER BY mrr DESC NULLS LAST"
        ))).fetchall()
    businesses = [
        {"id": r.id, "name": r.name, "slug": r.slug, "status": r.status,
         "mrr": float(r.mrr or 0), "customers": r.customers_count or 0,
         "kill_score": float(r.kill_score) if r.kill_score else None, "domain": r.domain}
        for r in rows
    ]
    return templates.TemplateResponse("businesses_list.html", {"request": request, "businesses": businesses})


def start():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)


if __name__ == "__main__":
    start()

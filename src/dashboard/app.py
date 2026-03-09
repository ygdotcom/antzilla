"""CEO Dashboard — FastAPI + HTMX + Tailwind.

Auth via Supabase (email/password). Session stored in HMAC-signed cookie.
First boot: /login → /setup wizard if no secrets configured.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import httpx

from src.config import settings
from src.db import SessionLocal
from src.dashboard.deps import (
    SESSION_COOKIE,
    _sign_token,
    check_password,
    get_current_user,
    templates,
    verify_credentials,
)

logger = structlog.get_logger()

app = FastAPI(title="Antzilla Dashboard", docs_url=None, redoc_url=None)

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
    "deep-scout": ("src.agents.deep_scout", "DeepScout", [
        "research_market", "analyze_us_competitor", "discover_channels",
        "research_regulations", "generate_gtm_playbook", "save_and_recommend"
    ]),
    "brand-designer": ("src.agents.brand_designer", "BrandDesigner", [
        "quick_brand"
    ]),
    "builder": ("src.agents.builder", "Builder", [
        "generate_architecture", "generate_code", "verify_rls",
        "create_github_repo", "push_template", "push_to_github",
        "deploy_vercel", "run_lighthouse", "finalize"
    ]),
}


async def run_build_pipeline(business_id: int):
    """Full build pipeline: Brand Designer → Builder. Runs in background."""
    import importlib
    from sqlalchemy import text as sa_text

    async def _pipeline():
        try:
            # Fetch business data
            async with SessionLocal() as db:
                biz = (await db.execute(sa_text(
                    "SELECT id, name, slug, niche, idea_id FROM businesses WHERE id = :id"
                ), {"id": business_id})).fetchone()
                if not biz:
                    logger.error("build_pipeline_no_business", business_id=business_id)
                    return

                # Fetch idea's scout report if available
                scout_report = ""
                if biz.idea_id:
                    idea = (await db.execute(sa_text(
                        "SELECT scout_report, ca_gap_analysis FROM ideas WHERE id = :id"
                    ), {"id": biz.idea_id})).fetchone()
                    if idea:
                        scout_report = idea.scout_report or idea.ca_gap_analysis or ""

                await db.execute(sa_text(
                    "UPDATE businesses SET status = 'building', updated_at = NOW() WHERE id = :id"
                ), {"id": business_id})

            # Notify Slack
            try:
                from src.slack import notify_build_started
                await notify_build_started(biz.name, business_id)
            except Exception:
                pass
                await db.execute(sa_text(
                    "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                    "VALUES ('build_pipeline', 'pipeline_started', :result, 'success', :biz_id)"
                ), {"result": json.dumps({"business": biz.name}), "biz_id": business_id})
                await db.commit()

            # --- STEP 1: Brand Designer (light mode) ---
            logger.info("build_pipeline_step", step="brand_designer", business=biz.name)

            class BrandContext:
                def __init__(self, biz_id, niche, scout):
                    self._input = {"business_id": biz_id, "niche": niche, "scout_report": scout}
                    self._outputs = {}
                def workflow_input(self):
                    return self._input
                def step_output(self, name):
                    return self._outputs.get(name, {})

            from src.agents.brand_designer import BrandDesigner
            designer = BrandDesigner()
            brand_ctx = BrandContext(business_id, biz.niche or "", scout_report)
            brand_result = await designer.quick_brand(brand_ctx)
            brand_kit = brand_result.get("brand_kit", {})

            async with SessionLocal() as db:
                await db.execute(sa_text(
                    "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                    "VALUES ('brand_designer', 'quick_brand_done', :result, 'success', :biz_id)"
                ), {
                    "result": json.dumps({
                        "recommended_name": brand_kit.get("recommended_name", ""),
                        "has_colors": bool(brand_kit.get("colors")),
                    }),
                    "biz_id": business_id,
                })
                await db.commit()

            # --- STEP 2: Architecture + Copywriter + Builder ---
            logger.info("build_pipeline_step", step="builder", business=biz.name)

            class BuilderContext:
                def __init__(self, biz_id, niche, scout, brand, github=""):
                    self._input = {
                        "business_id": biz_id, "niche": niche,
                        "scout_report": scout, "brand_kit": brand,
                        "github_repo": github,
                    }
                    self._outputs = {}
                def workflow_input(self):
                    return self._input
                def step_output(self, name):
                    return self._outputs.get(name, {})

            from src.agents.builder import Builder
            builder = Builder()
            build_ctx = BuilderContext(business_id, biz.niche or "", scout_report, brand_kit)

            # Step 2a: Generate architecture
            logger.info("builder_step", step="generate_architecture", business=biz.name)
            arch_result = await builder.generate_architecture(build_ctx)
            build_ctx._outputs["generate_architecture"] = arch_result if isinstance(arch_result, dict) else {}

            # Step 2b: Copywriter generates FR+EN messages
            logger.info("build_pipeline_step", step="copywriter", business=biz.name)
            from src.agents.copywriter import Copywriter

            class CopyContext:
                def __init__(self, biz_id, arch, brand, niche, scout):
                    self._input = {
                        "business_id": biz_id,
                        "architecture": arch,
                        "brand_kit": brand,
                        "niche": niche,
                        "scout_report": scout,
                    }
                def workflow_input(self):
                    return self._input
                def step_output(self, name):
                    return {}

            copywriter = Copywriter()
            copy_ctx = CopyContext(
                business_id,
                arch_result.get("architecture", {}),
                brand_kit,
                biz.niche or "",
                scout_report,
            )
            copy_result = await copywriter.generate_copy(copy_ctx)

            # Inject messages into builder context so code gen can reference them
            build_ctx._input["messages_fr"] = copy_result.get("messages_fr", {})
            build_ctx._input["messages_en"] = copy_result.get("messages_en", {})
            build_ctx._input["app_name"] = copy_result.get("app_name", "")

            # Step 2c: Build the app (v0 API or Claude fallback)
            v0_key = settings.get("V0_API_KEY")

            if v0_key:
                # v0 PATH: one API call builds + deploys the entire app
                logger.info("builder_step", step="build_with_v0", business=biz.name)
                v0_result = await builder.build_with_v0(build_ctx)
                build_ctx._outputs["generate_code"] = v0_result
                deployment_url_override = v0_result.get("deployment_url", "")
                if deployment_url_override:
                    # v0 handles deploy — skip our template/push/vercel steps
                    build_ctx._outputs["finalize"] = {
                        "deployment_url": deployment_url_override,
                        "github_repo": "",
                        "files_pushed": v0_result.get("v0_result", {}).get("file_count", 0),
                    }
            else:
                # FALLBACK PATH: Claude code gen + template + GitHub + Vercel
                remaining_steps = [
                    ("generate_code", builder.generate_code),
                    ("verify_rls", builder.verify_rls),
                    ("create_github_repo", builder.create_github_repo),
                    ("push_template", builder.push_template),
                    ("push_to_github", builder.push_to_github),
                    ("deploy_vercel", builder.deploy_vercel),
                    ("run_lighthouse", builder.run_lighthouse),
                    ("finalize", builder.finalize),
                ]
                for step_name, step_fn in remaining_steps:
                    logger.info("builder_step", step=step_name, business=biz.name)
                    result = await step_fn(build_ctx)
                    build_ctx._outputs[step_name] = result if isinstance(result, dict) else {}

            finalize_result = build_ctx._outputs.get("finalize", {})
            deployment_url = finalize_result.get("deployment_url", "")
            github_repo = finalize_result.get("github_repo", "")

            # --- STEP 3: Infra Setup (non-fatal — skips what it can't do) ---
            logger.info("build_pipeline_step", step="infra_setup", business=biz.name)
            try:
                from src.agents.infra_setup import InfraSetup
                infra = InfraSetup()

                vercel_pid = ""
                async with SessionLocal() as db:
                    biz_row = (await db.execute(sa_text(
                        "SELECT vercel_project_id FROM businesses WHERE id = :id"
                    ), {"id": business_id})).fetchone()
                    if biz_row:
                        vercel_pid = biz_row.vercel_project_id or ""

                architecture = build_ctx._outputs.get("generate_architecture", {}).get("architecture", {})
                pricing = architecture.get("pricing")

                code_output = build_ctx._outputs.get("generate_code", {}).get("code_output", {})
                migrations_sql = ""
                for mig in code_output.get("migrations", []):
                    if mig.get("content"):
                        migrations_sql += mig["content"] + "\n"

                sb_result = await infra.setup_supabase(business_id, biz.slug or "", migrations_sql)
                st_result = {"success": False, "error": "skipped"}
                wh_result = {}
                try:
                    st_result = await infra.setup_stripe(business_id, biz.name, biz.slug or "", pricing)
                except Exception as stripe_exc:
                    logger.warning("stripe_setup_skipped", error=str(stripe_exc))

                if deployment_url and st_result.get("success"):
                    try:
                        wh_result = await infra.create_stripe_webhook(business_id, deployment_url)
                    except Exception as wh_exc:
                        logger.warning("stripe_webhook_skipped", error=str(wh_exc))

                if vercel_pid:
                    try:
                        await infra.set_vercel_env_vars(
                            business_id, vercel_pid, deployment_url,
                            st_result.get("stripe_config", {}),
                            wh_result.get("webhook_secret", ""),
                        )
                    except Exception as env_exc:
                        logger.warning("vercel_env_skipped", error=str(env_exc))

                async with SessionLocal() as db:
                    await db.execute(sa_text(
                        "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                        "VALUES ('infra_setup', 'setup_complete', :result, 'success', :biz_id)"
                    ), {
                        "result": json.dumps({
                            "supabase": sb_result.get("success"),
                            "stripe": st_result.get("success"),
                            "webhook": wh_result.get("success") if wh_result else None,
                        }),
                        "biz_id": business_id,
                    })
                    await db.commit()

                # Redeploy with env vars
                if deployment_url and vercel_pid:
                    try:
                        vercel_token = settings.get("VERCEL_TOKEN")
                        gh_token = settings.get("GITHUB_TOKEN")
                        async with httpx.AsyncClient(timeout=30) as vc:
                            gh_resp = await vc.get(
                                f"https://api.github.com/repos/{github_repo}",
                                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                            )
                            repo_id = str(gh_resp.json().get("id", "")) if gh_resp.status_code == 200 else ""
                            if repo_id:
                                await vc.post(
                                    "https://api.vercel.com/v13/deployments",
                                    headers={"Authorization": f"Bearer {vercel_token}", "Content-Type": "application/json"},
                                    json={"name": (biz.slug or ""), "gitSource": {"type": "github", "repoId": repo_id, "ref": "main"}},
                                )
                    except Exception as redeploy_exc:
                        logger.warning("vercel_redeploy_failed", error=str(redeploy_exc))
            except Exception as infra_exc:
                logger.warning("infra_setup_failed_nonfatal", error=str(infra_exc))

            # --- STEP 4: Design QA (logo + review) ---
            logger.info("build_pipeline_step", step="design_qa", business=biz.name)

            class DesignContext:
                def __init__(self, biz_id, brand, url):
                    self._input = {"business_id": biz_id, "brand_kit": brand, "deployment_url": url}
                    self._outputs = {}
                def workflow_input(self):
                    return self._input
                def step_output(self, name):
                    return self._outputs.get(name, {})

            from src.agents.design_qa import DesignQA
            designer = DesignQA()
            design_ctx = DesignContext(business_id, brand_kit, deployment_url)

            for step_name, step_fn in [
                ("generate_logo", designer.generate_logo),
                ("screenshot_and_review", designer.screenshot_and_review),
                ("apply_fixes", designer.apply_fixes),
            ]:
                logger.info("design_qa_step", step=step_name, business=biz.name)
                result = await step_fn(design_ctx)
                design_ctx._outputs[step_name] = result if isinstance(result, dict) else {}

            qa_result = design_ctx._outputs.get("apply_fixes", {})

            async with SessionLocal() as db:
                await db.execute(sa_text(
                    "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                    "VALUES ('build_pipeline', 'pipeline_complete', :result, 'success', :biz_id)"
                ), {
                    "result": json.dumps({
                        "github_repo": finalize_result.get("github_repo", ""),
                        "files_pushed": finalize_result.get("files_pushed", 0),
                        "deployment_url": deployment_url,
                        "design_score": qa_result.get("overall_score"),
                        "logo_pushed": qa_result.get("logo_pushed", 0),
                    }),
                    "biz_id": business_id,
                })
                await db.commit()

            logger.info("build_pipeline_complete", business=biz.name,
                        repo=finalize_result.get("github_repo"),
                        design_score=qa_result.get("overall_score"))

            # Notify Slack: build complete
            try:
                from src.slack import notify_build_complete
                total_cost = sum(
                    build_ctx._outputs.get(s, {}).get("cost_usd", 0) or 0
                    for s in ["generate_architecture", "generate_code"]
                )
                total_cost += (brand_result.get("cost_usd", 0) or 0)
                total_cost += (copy_result.get("cost_usd", 0) or 0) if copy_result else 0
                await notify_build_complete(
                    biz.name,
                    finalize_result.get("github_repo", ""),
                    deployment_url,
                    total_cost,
                )
            except Exception as slack_exc:
                logger.warning("slack_notify_failed", error=str(slack_exc))

        except Exception as exc:
            logger.error("build_pipeline_failed", business_id=business_id,
                         error=str(exc), error_type=type(exc).__name__)
            try:
                async with SessionLocal() as db:
                    await db.execute(sa_text(
                        "INSERT INTO agent_logs (agent_name, action, result, status, business_id) "
                        "VALUES ('build_pipeline', 'pipeline_failed', :result, 'error', :biz_id)"
                    ), {"result": json.dumps({"error": str(exc)}), "biz_id": business_id})
                    await db.commit()
            except Exception:
                pass

            # Notify Slack: build failed
            try:
                from src.slack import notify_build_failed
                biz_name = biz.name if biz else f"business_{business_id}"
                await notify_build_failed(biz_name, str(exc))
            except Exception as slack_exc:
                logger.warning("slack_notify_failed", error=str(slack_exc))

    import asyncio
    asyncio.create_task(_pipeline())


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


@app.get("/api/notifications/count", response_class=HTMLResponse)
async def notification_count(request: Request):
    """Returns the notification badge HTML — polled every 10s by HTMX."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("")
    from sqlalchemy import text as sa_text
    from src.db import SessionLocal
    try:
        async with SessionLocal() as db:
            row = (await db.execute(sa_text(
                "SELECT "
                "(SELECT COUNT(*) FROM ideas WHERE status = 'validated') + "
                "(SELECT COUNT(*) FROM leads WHERE status = 'pending_approval') "
                "AS total"
            ))).fetchone()
            count = row.total or 0
        if count > 0:
            return HTMLResponse(
                f'<span class="flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-xs font-bold">{count}</span>'
            )
    except Exception:
        pass
    return HTMLResponse("")


@app.get("/api/notifications/list", response_class=HTMLResponse)
async def notification_list(request: Request):
    """Returns dropdown HTML with pending items."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("")
    from sqlalchemy import text as sa_text
    from src.db import SessionLocal
    items = []
    try:
        async with SessionLocal() as db:
            ideas = (await db.execute(sa_text(
                "SELECT id, name, score FROM ideas WHERE status = 'validated' ORDER BY score DESC LIMIT 10"
            ))).fetchall()
            for i in ideas:
                items.append(
                    f'<a href="/ideas/{i.id}" class="block px-4 py-3 hover:bg-zinc-800 border-b border-zinc-800/50">'
                    f'<p class="text-white text-sm font-medium">Approve idea?</p>'
                    f'<p class="text-zinc-400 text-xs">{i.name} — score {float(i.score or 0):.1f}</p></a>'
                )
            outreach = (await db.execute(sa_text(
                "SELECT COUNT(*) AS cnt FROM leads WHERE status = 'pending_approval'"
            ))).fetchone()
            if outreach.cnt and outreach.cnt > 0:
                items.append(
                    f'<a href="/decisions" class="block px-4 py-3 hover:bg-zinc-800 border-b border-zinc-800/50">'
                    f'<p class="text-white text-sm font-medium">Outreach approval</p>'
                    f'<p class="text-zinc-400 text-xs">{outreach.cnt} messages waiting for review</p></a>'
                )
    except Exception:
        pass
    if not items:
        return HTMLResponse(
            '<div class="px-4 py-6 text-center text-zinc-500 text-sm">No pending actions</div>'
        )
    return HTMLResponse("".join(items))


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

"""Idea pipeline page + manual idea submission with AI scoring."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from src.dashboard.deps import templates, verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/ideas")

SCORE_IDEA_PROMPT = """\
Tu es l'évaluateur d'idées SaaS pour le marché canadien.

IMPORTANT: La factory ne peut construire que des outils SIMPLES — 5-10 écrans max, buildable en 2 semaines avec IA.
REJETER automatiquement si: concurrent US a 100+ employés, a levé $10M+, ou le produit est une PLATEFORME (CRM, POS, ERP).
ON CHERCHE: petits outils verticaux ($29-99/mo) qui automatisent UNE tâche ennuyeuse.

Score-la sur ces 13 critères (/10 chacun):
1. Douleur client (récurrence, intensité)
2. Willingness to pay (le client paie-t-il déjà aux US?)
3. Defensibilité vs ChatGPT
4. Taille du marché CA (minimum 5000 entreprises cibles)
5. Compétition locale au Canada (moins = mieux)
6. ARPU potentiel ($29-99/mo = bien, $500+/mo = trop enterprise)
7. Complexité technique du MVP — DOIT être buildable en <2 semaines. Score <7 = REJETER.
8. Time to first revenue (<60 jours = bien)
9. Potentiel de récurrence (MRR vs one-time)
10. Avantage bilingue/canadien spécifique
11. Potentiel d'expansion internationale
12. Compatibilité avec notre stack (Next.js, Supabase, Stripe)
13. Taille du concurrent US — 1-5 emp = 10, 5-20 = 8, 20-50 = 5, 50-100 = 3, 100+ = 1 (REJETER)

Réponds UNIQUEMENT en JSON:
{
  "score": 7.5,
  "scoring_details": {"criterion_1": 8, ..., "criterion_13": 9},
  "ca_gap_analysis": "Why this doesn't exist in Canada yet",
  "tam_estimate": "~X businesses in Canada",
  "pricing_hypothesis": "$X/mo based on Y",
  "mvp_complexity": "low|medium|high",
  "core_screens": 5,
  "recommendation": "GO|MAYBE|PASS",
  "reasoning": "2-3 sentences explaining the score"
}
"""


@router.get("", response_class=HTMLResponse)
async def ideas_page(
    request: Request,
    user: str = Depends(verify_credentials),
    status: str = "",
    sort: str = "score",
    q: str = "",
):
    # Build query with filters
    conditions = []
    params: dict = {}

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if q:
        conditions.append("(name ILIKE :q OR niche ILIKE :q OR us_equivalent ILIKE :q)")
        params["q"] = f"%{q}%"

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sort_map = {
        "score": "score DESC NULLS LAST",
        "score_asc": "score ASC NULLS LAST",
        "newest": "created_at DESC",
        "oldest": "created_at ASC",
        "name": "name ASC",
    }
    order = sort_map.get(sort, "score DESC NULLS LAST")

    async with SessionLocal() as db:
        all_ideas = (await db.execute(text(
            f"SELECT id, name, niche, us_equivalent, score, status, created_at "
            f"FROM ideas {where} ORDER BY {order}"
        ), params)).fetchall()

    return templates.TemplateResponse("ideas.html", {
        "request": request,
        "ideas": [
            {"id": i.id, "name": i.name, "niche": i.niche,
             "us_equivalent": i.us_equivalent, "score": float(i.score) if i.score else None,
             "status": i.status, "at": i.created_at.isoformat() if i.created_at else ""}
            for i in all_ideas
        ],
        "current_status": status,
        "current_sort": sort,
        "current_q": q,
    })


@router.get("/{idea_id}", response_class=HTMLResponse)
async def idea_detail(request: Request, idea_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        idea = (await db.execute(text(
            "SELECT id, name, niche, us_equivalent, us_equivalent_url, score, "
            "scoring_details, status, scout_report, ca_gap_analysis, created_at "
            "FROM ideas WHERE id = :id"
        ), {"id": idea_id})).fetchone()

    if not idea:
        return HTMLResponse("<h1>Idea not found</h1>", status_code=404)

    return templates.TemplateResponse("idea_detail.html", {
        "request": request,
        "idea": {
            "id": idea.id, "name": idea.name, "niche": idea.niche,
            "us_equivalent": idea.us_equivalent, "url": idea.us_equivalent_url,
            "score": float(idea.score) if idea.score else None,
            "status": idea.status, "scout_report": idea.scout_report or "",
            "gap": idea.ca_gap_analysis,
        },
    })


async def _log_idea_event(db, idea_id: int, action: str, old_status: str, new_status: str):
    """Log every idea status change to agent_logs so it appears in the Console."""
    await db.execute(
        text(
            "INSERT INTO agent_logs (agent_name, action, result, status) "
            "VALUES ('ceo_dashboard', :action, :result, 'success')"
        ),
        {
            "action": action,
            "result": json.dumps({"idea_id": idea_id, "from": old_status, "to": new_status}),
        },
    )


@router.post("/{idea_id}/advance", response_class=HTMLResponse)
async def advance_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance new → scouting. Logs to console."""
    async with SessionLocal() as db:
        row = (await db.execute(text("SELECT name, status FROM ideas WHERE id = :id"), {"id": idea_id})).fetchone()
        if not row or row.status != "new":
            return HTMLResponse('<span class="text-zinc-500">Cannot advance</span>')
        await db.execute(text("UPDATE ideas SET status = 'scouting', updated_at = NOW() WHERE id = :id"), {"id": idea_id})
        await _log_idea_event(db, idea_id, f"idea_advanced: {row.name}", "new", "scouting")
        await db.commit()
    return HTMLResponse('<span class="text-blue-400">→ Scouting</span>')


@router.post("/{idea_id}/validate", response_class=HTMLResponse)
async def validate_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance scouting → validated. Logs to console."""
    async with SessionLocal() as db:
        row = (await db.execute(text("SELECT name, status FROM ideas WHERE id = :id"), {"id": idea_id})).fetchone()
        if not row:
            return HTMLResponse('<span class="text-zinc-500">Not found</span>')
        await db.execute(text("UPDATE ideas SET status = 'validated', updated_at = NOW() WHERE id = :id"), {"id": idea_id})
        await _log_idea_event(db, idea_id, f"idea_validated: {row.name}", row.status, "validated")
        await db.commit()
    return HTMLResponse('<span class="text-green-400">→ Validated</span>')


@router.post("/{idea_id}/approve", response_class=HTMLResponse)
async def approve_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Approve idea → create business → auto-trigger Brand Designer + Builder."""
    async with SessionLocal() as db:
        row = (await db.execute(text(
            "SELECT id, name, niche, status FROM ideas WHERE id = :id"
        ), {"id": idea_id})).fetchone()
        if not row:
            return HTMLResponse('<span class="text-zinc-500">Not found</span>')

        await db.execute(text("UPDATE ideas SET status = 'approved', updated_at = NOW() WHERE id = :id"), {"id": idea_id})

        slug = (row.name or "unnamed").lower().replace(" ", "-").replace("'", "")[:50]
        existing = (await db.execute(text("SELECT id FROM businesses WHERE idea_id = :id"), {"id": idea_id})).fetchone()
        business_id = None
        if existing:
            business_id = existing.id
        else:
            biz_row = (await db.execute(
                text(
                    "INSERT INTO businesses (idea_id, name, slug, niche, status) "
                    "VALUES (:idea_id, :name, :slug, :niche, 'setup') RETURNING id"
                ),
                {"idea_id": idea_id, "name": row.name, "slug": slug, "niche": row.niche},
            )).fetchone()
            business_id = biz_row.id

        await _log_idea_event(db, idea_id, f"idea_approved: {row.name} → business created, build pipeline starting", row.status, "approved")
        await db.commit()

    # Auto-trigger the build pipeline (Brand Designer → Builder)
    if business_id:
        from src.dashboard.app import run_build_pipeline
        await run_build_pipeline(business_id)

    return HTMLResponse(
        '<span class="text-brand animate-pulse">→ Approved — building started (Brand → Code → GitHub)... check Console</span>'
    )


@router.post("/{idea_id}/archive", response_class=HTMLResponse)
async def archive_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Kill an idea. Logs to console."""
    async with SessionLocal() as db:
        row = (await db.execute(text("SELECT name, status FROM ideas WHERE id = :id"), {"id": idea_id})).fetchone()
        if not row:
            return HTMLResponse('<span class="text-zinc-500">Not found</span>')
        await db.execute(text("UPDATE ideas SET status = 'killed', kill_reason = 'Archived by CEO', updated_at = NOW() WHERE id = :id"), {"id": idea_id})
        await _log_idea_event(db, idea_id, f"idea_killed: {row.name}", row.status, "killed")
        await db.commit()
    return HTMLResponse('<span class="text-zinc-500">Killed</span>')


class IdeaProposal(BaseModel):
    name: str
    niche: str
    us_equivalent: str = ""
    us_equivalent_url: str = ""
    description: str = ""


@router.post("/propose", response_class=HTMLResponse)
async def propose_idea(req: IdeaProposal, user: str = Depends(verify_credentials)):
    """CEO proposes an idea → Claude scores it on 12 criteria → saved to ideas table."""
    from src.llm import call_claude

    user_msg = json.dumps({
        "name": req.name,
        "niche": req.niche,
        "us_equivalent": req.us_equivalent,
        "us_equivalent_url": req.us_equivalent_url,
        "description": req.description,
    })

    try:
        response_text, cost = await call_claude(
            model_tier="sonnet",
            system=SCORE_IDEA_PROMPT,
            user=user_msg,
            max_tokens=2048,
            temperature=0.3,
        )

        # Parse the scoring
        clean = response_text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            clean = "\n".join(lines)
        try:
            scoring = json.loads(clean)
        except json.JSONDecodeError:
            start = clean.find("{")
            end = clean.rfind("}")
            if start >= 0 and end > start:
                scoring = json.loads(clean[start : end + 1])
            else:
                scoring = {"score": 5.0, "scoring_details": {}, "ca_gap_analysis": "Scoring failed"}

        score = float(scoring.get("score", 5.0))
        details = scoring.get("scoring_details", {})
        gap = scoring.get("ca_gap_analysis", "")
        reasoning = scoring.get("reasoning", "")

        async with SessionLocal() as db:
            row = (await db.execute(
                text(
                    "INSERT INTO ideas (name, niche, us_equivalent, us_equivalent_url, "
                    "ca_gap_analysis, score, scoring_details, status) "
                    "VALUES (:name, :niche, :us_eq, :us_url, :gap, :score, :details, 'new') "
                    "RETURNING id"
                ),
                {
                    "name": req.name,
                    "niche": req.niche,
                    "us_eq": req.us_equivalent,
                    "us_url": req.us_equivalent_url,
                    "gap": f"{gap}\n\n{reasoning}".strip(),
                    "score": score,
                    "details": json.dumps(details),
                },
            )).fetchone()
            await db.execute(
                text(
                    "INSERT INTO agent_logs (agent_name, action, result, cost_usd, status) "
                    "VALUES ('idea_factory', 'ceo_proposal', :result, :cost, 'success')"
                ),
                {"result": json.dumps({"idea": req.name, "score": score}), "cost": cost},
            )
            await db.commit()

        rec = scoring.get("recommendation", "MAYBE")
        color = "text-brand" if rec == "GO" else "text-yellow-400" if rec == "MAYBE" else "text-red-400"

        return HTMLResponse(
            f'<div class="p-4 rounded-lg bg-zinc-800 border border-zinc-700 space-y-2">'
            f'<div class="flex items-center justify-between">'
            f'<span class="text-white font-semibold">{req.name}</span>'
            f'<span class="text-2xl font-bold {color}">{score:.1f}/10</span>'
            f'</div>'
            f'<p class="text-zinc-400 text-sm">{reasoning}</p>'
            f'<p class="{color} text-sm font-medium">Recommendation: {rec}</p>'
            f'<a href="/ideas/{row.id}" class="text-brand text-sm hover:underline">View details →</a>'
            f'</div>'
        )

    except Exception as exc:
        return HTMLResponse(
            f'<div class="text-red-400 text-sm p-3">Scoring failed: {exc}</div>'
        )

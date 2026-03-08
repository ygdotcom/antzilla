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

Tu reçois une idée proposée par le CEO. Score-la sur ces 12 critères (/10 chacun):
1. Douleur client (récurrence, intensité)
2. Willingness to pay (le client paie-t-il déjà aux US?)
3. Defensibilité vs ChatGPT
4. Taille du marché CA (minimum 5000 entreprises cibles)
5. Compétition locale au Canada (moins = mieux)
6. ARPU potentiel (>$100/mo = bien)
7. Complexité technique du MVP (moins = mieux)
8. Time to first revenue (<60 jours = bien)
9. Potentiel de récurrence (MRR vs one-time)
10. Avantage bilingue/canadien spécifique
11. Potentiel d'expansion internationale
12. Compatibilité avec notre stack (Next.js, Supabase, Stripe)

Réponds UNIQUEMENT en JSON:
{
  "score": 7.5,
  "scoring_details": {"criterion_1": 8, "criterion_2": 7, ...},
  "ca_gap_analysis": "Why this doesn't exist in Canada yet",
  "tam_estimate": "~X businesses in Canada",
  "pricing_hypothesis": "$X/mo based on Y",
  "mvp_complexity": "low|medium|high",
  "recommendation": "GO|MAYBE|PASS",
  "reasoning": "2-3 sentences explaining the score"
}
"""


@router.get("", response_class=HTMLResponse)
async def ideas_page(request: Request, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        all_ideas = (await db.execute(text(
            "SELECT id, name, niche, us_equivalent, score, status, created_at "
            "FROM ideas ORDER BY score DESC NULLS LAST, created_at DESC"
        ))).fetchall()

    return templates.TemplateResponse("ideas.html", {
        "request": request,
        "ideas": [
            {"id": i.id, "name": i.name, "niche": i.niche,
             "us_equivalent": i.us_equivalent, "score": float(i.score) if i.score else None,
             "status": i.status, "at": i.created_at.isoformat() if i.created_at else ""}
            for i in all_ideas
        ],
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


@router.post("/{idea_id}/advance", response_class=HTMLResponse)
async def advance_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance new → scouting."""
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'scouting' WHERE id = :id AND status = 'new'"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Advanced</span>')


@router.post("/{idea_id}/validate", response_class=HTMLResponse)
async def validate_idea(idea_id: int, user: str = Depends(verify_credentials)):
    """Advance scouting → validated."""
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'validated' WHERE id = :id AND status = 'scouting'"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-green-400">Advanced to Validation</span>')


@router.post("/{idea_id}/archive", response_class=HTMLResponse)
async def archive_idea(idea_id: int, user: str = Depends(verify_credentials)):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE ideas SET status = 'killed', kill_reason = 'Archived by CEO' WHERE id = :id"), {"id": idea_id})
        await db.commit()
    return HTMLResponse('<span class="text-zinc-500">Archived</span>')


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

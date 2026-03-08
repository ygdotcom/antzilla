"""Agent 14: Social Proof Collector.

Event-driven: NPS >= 8, referral made, 14 days active usage.
Sends testimonial requests, collects responses, publishes to site,
requests external reviews (Google/Capterra), updates aggregate metrics.
"""

from __future__ import annotations

import base64
import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses, load_playbook
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

NPS_THRESHOLD = 8
ACTIVE_DAYS_THRESHOLD = 14

TESTIMONIAL_REQUEST_PROMPT = """\
Tu génères un email court demandant un témoignage à un client satisfait.

Tu reçois: nom du client, entreprise, produit, langue.

RÈGLES:
- Ton chaleureux et reconnaissant
- Demande concise (2-3 phrases)
- Lien vers formulaire de témoignage
- Bilingue selon la langue du client (FR québécois ou EN canadien)

Réponds en JSON: {"subject": "...", "body": "..."}
"""


class SocialProof(BaseAgent):
    """Collects testimonials, publishes to site, requests external reviews."""

    agent_name = "social_proof"
    default_model = "haiku"

    async def find_candidates(self, context) -> dict:
        """Query customers with NPS >= 8 or 14+ days active."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"candidates": []}

        candidates = []
        async with SessionLocal() as db:
            for biz in businesses:
                rows = (
                    await db.execute(
                        text(
                            "SELECT c.id, c.name, c.email, c.company, c.language, c.nps_score, "
                            "c.last_active_at, c.created_at "
                            "FROM customers c "
                            "WHERE c.business_id = :biz AND c.status IN ('trial', 'active') "
                            "AND (c.nps_score >= :nps OR "
                            "  (c.last_active_at IS NOT NULL AND c.last_active_at > NOW() - INTERVAL '14 days')) "
                            "ORDER BY c.nps_score DESC NULLS LAST LIMIT 30"
                        ),
                        {"biz": biz["id"], "nps": NPS_THRESHOLD},
                    )
                ).fetchall()

                for r in rows:
                    candidates.append({
                        "id": r.id,
                        "name": r.name or "",
                        "email": r.email,
                        "company": r.company or "",
                        "language": r.language or "fr",
                        "nps_score": r.nps_score,
                        "business_id": biz["id"],
                        "business_name": biz["name"],
                    })

        await self.log_execution(
            action="find_candidates",
            result={"count": len(candidates)},
        )
        return {"candidates": candidates}

    async def send_testimonial_request(self, context) -> dict:
        """Email asking for testimonial."""
        find_out = context.step_output("find_candidates")
        candidates = find_out.get("candidates", [])

        if not candidates or not settings.RESEND_API_KEY:
            return {"sent": 0}

        playbook = await load_playbook(candidates[0]["business_id"]) if candidates else {}
        messaging = playbook.get("messaging", {}) if playbook else {}

        sent = 0
        for c in candidates[:15]:
            model_tier = await self.check_budget()
            user_prompt = json.dumps({
                "customer_name": c["name"],
                "company": c["company"],
                "product": c["business_name"],
                "language": c["language"],
                "messaging": messaging,
            }, default=str)

            response, cost = await call_claude(
                model_tier=model_tier,
                system=TESTIMONIAL_REQUEST_PROMPT,
                user=user_prompt,
                max_tokens=512,
                temperature=0.5,
            )

            try:
                msg = json.loads(response)
            except json.JSONDecodeError:
                msg = {"subject": "Partagez votre expérience", "body": response[:500]}

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                        json={
                            "from": "feedback@factorylabs.ca",
                            "to": c["email"],
                            "subject": msg.get("subject", ""),
                            "text": msg.get("body", ""),
                        },
                    )
                sent += 1
                await self.log_execution(
                    action="testimonial_request_sent",
                    result={"customer_id": c["id"]},
                    cost_usd=cost,
                    business_id=c["business_id"],
                )
            except Exception as exc:
                logger.warning("testimonial_request_failed", email=c["email"][:10] + "...", error=str(exc))

        return {"sent": sent}

    async def collect_response(self, context) -> dict:
        """Process submitted testimonials (from webhook or DB poll)."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        testimonials = input_data.get("testimonials", [])

        if not testimonials:
            async with SessionLocal() as db:
                rows = (
                    await db.execute(
                        text(
                            "SELECT id, business_id, customer_id, content_fr, content_en, "
                            "customer_name, permission_granted "
                            "FROM testimonials "
                            "WHERE published = FALSE AND permission_granted = TRUE "
                            "LIMIT 20"
                        )
                    )
                ).fetchall()
            testimonials = [
                {
                    "id": r.id,
                    "business_id": r.business_id,
                    "customer_id": r.customer_id,
                    "content_fr": r.content_fr,
                    "content_en": r.content_en,
                    "customer_name": r.customer_name,
                    "permission_granted": r.permission_granted,
                }
                for r in rows
            ]

        await self.log_execution(
            action="collect_response",
            result={"count": len(testimonials)},
        )
        return {"testimonials": testimonials}

    async def publish_to_site(self, context) -> dict:
        """Update GitHub repo testimonials section."""
        collect_out = context.step_output("collect_response")
        testimonials = collect_out.get("testimonials", [])

        if not testimonials or not settings.GITHUB_TOKEN:
            return {"published": 0}

        published = 0
        for t in testimonials:
            if not t.get("permission_granted"):
                continue
            biz_id = t.get("business_id")
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        text("SELECT github_repo FROM businesses WHERE id = :id"),
                        {"id": biz_id},
                    )
                ).fetchone()
            repo = row.github_repo if row else None
            if not repo:
                continue

            content_fr = t.get("content_fr") or ""
            content_en = t.get("content_en") or content_fr
            section = f"## Témoignages\n\n**FR:** {content_fr}\n\n**EN:** {content_en}\n"

            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    encoded = base64.b64encode(section.encode()).decode()
                    payload = {
                        "message": "chore: add testimonial",
                        "content": encoded,
                    }
                    await client.put(
                        f"https://api.github.com/repos/{repo}/contents/testimonials.md",
                        headers={
                            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                            "Accept": "application/vnd.github+json",
                        },
                        json=payload,
                    )
                published += 1
                async with SessionLocal() as db:
                    await db.execute(
                        text(
                            "UPDATE testimonials SET published = TRUE, published_where = 'github' "
                            "WHERE id = :id"
                        ),
                        {"id": t["id"]},
                    )
                    await db.commit()
            except Exception as exc:
                logger.warning("publish_testimonial_failed", repo=repo, error=str(exc))

        await self.log_execution(action="publish_to_site", result={"published": published})
        return {"published": published}

    async def request_external_review(self, context) -> dict:
        """Send links for Google/Capterra reviews."""
        collect_out = context.step_output("collect_response")
        testimonials = collect_out.get("testimonials", [])

        if not testimonials or not settings.RESEND_API_KEY:
            return {"sent": 0}

        sent = 0
        for t in testimonials:
            if not t.get("permission_granted"):
                continue
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        text(
                            "SELECT c.email, c.language, b.name AS biz_name, b.domain "
                            "FROM customers c JOIN businesses b ON c.business_id = b.id "
                            "WHERE c.id = :cid"
                        ),
                        {"cid": t.get("customer_id")},
                    )
                ).fetchone()
            if not row or not row.email:
                continue

            google_link = "https://g.page/r/..."
            capterra_link = "https://www.capterra.com/..."
            body = (
                f"Merci pour votre témoignage! Pourriez-vous aussi nous laisser "
                f"un avis sur Google ({google_link}) ou Capterra ({capterra_link})?"
            )
            if row.language == "en":
                body = (
                    f"Thanks for your testimonial! Could you also leave us "
                    f"a review on Google ({google_link}) or Capterra ({capterra_link})?"
                )

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                        json={
                            "from": "reviews@factorylabs.ca",
                            "to": row.email,
                            "subject": "Avis Google / Capterra" if row.language == "fr" else "Google / Capterra Review",
                            "text": body,
                        },
                    )
                sent += 1
            except Exception as exc:
                logger.warning("external_review_request_failed", error=str(exc))

        await self.log_execution(action="request_external_review", result={"sent": sent})
        return {"sent": sent}

    async def update_aggregate_metrics(self, context) -> dict:
        """Count total deliverables: 'X devis créés au Canada'."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"updated": 0}

        async with SessionLocal() as db:
            for biz in businesses:
                playbook = await load_playbook(biz["id"])
                if not playbook:
                    continue
                icp = playbook.get("icp", {})
                niche = icp.get("niche", biz.get("slug", ""))

                rows = (
                    await db.execute(
                        text(
                            "SELECT COUNT(*) AS cnt FROM content "
                            "WHERE business_id = :biz AND status IN ('draft', 'published')"
                        ),
                        {"biz": biz["id"]},
                    )
                ).fetchall()
                count = rows[0].cnt if rows else 0

                metric_fr = f"{count} devis créés au Canada" if "devis" in niche else f"{count} livrables au Canada"
                metric_en = f"{count} quotes created in Canada" if "quote" in niche else f"{count} deliverables in Canada"

                await db.execute(
                    text(
                        "UPDATE businesses SET config = jsonb_set("
                        "COALESCE(config, '{}'::jsonb), '{aggregate_metrics}', :metrics::jsonb) "
                        "WHERE id = :id"
                    ),
                    {"id": biz["id"], "metrics": json.dumps({"fr": metric_fr, "en": metric_en})},
                )
            await db.commit()

        await self.log_execution(action="update_aggregate_metrics", result={"businesses": len(businesses)})
        return {"updated": len(businesses)}


def register(hatchet_instance):
    agent = SocialProof()
    wf = hatchet_instance.workflow(name="social-proof")

    @wf.task(execution_timeout="5m", retries=1)
    async def find_candidates(input, ctx):
        return await agent.find_candidates(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def send_testimonial_request(input, ctx):
        return await agent.send_testimonial_request(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def collect_response(input, ctx):
        return await agent.collect_response(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def publish_to_site(input, ctx):
        return await agent.publish_to_site(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def request_external_review(input, ctx):
        return await agent.request_external_review(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def update_aggregate_metrics(input, ctx):
        return await agent.update_aggregate_metrics(ctx)

    return wf

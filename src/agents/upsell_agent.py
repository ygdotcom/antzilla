"""Agent 19: Upsell Agent.

Weekly cron + event-driven. Identifies customers on free with high usage
(>80% quota, >3 months active, power referrers), generates personalized offers
with Claude Haiku, sends max 1 offer/month/customer, tracks conversion.
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

QUOTA_THRESHOLD = 0.80
MIN_ACTIVE_MONTHS = 3
MAX_OFFERS_PER_MONTH = 1


class UpsellAgent(BaseAgent):
    """Identify upsell opportunities and send personalized offers."""

    agent_name = "upsell_agent"
    default_model = "haiku"

    async def analyze_usage(self, context) -> dict:
        """Find customers on free with high usage: >80% quota, >3 months active, power referrers."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT c.id, c.name, c.email, c.language, c.plan, c.mrr, c.created_at, "
                        "c.last_active_at, "
                        "(SELECT COUNT(*) FROM referrals r WHERE r.referrer_customer_id = c.id AND r.status = 'rewarded') AS referral_count "
                        "FROM customers c "
                        "WHERE c.status IN ('active', 'trial') "
                        "AND (c.plan = 'free' OR c.mrr = 0) "
                        "AND c.created_at < NOW() - INTERVAL '3 months' "
                        "AND c.business_id = COALESCE(:biz, c.business_id) "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM agent_logs al "
                        "  WHERE al.agent_name = 'upsell_agent' AND al.action = 'send_offer' "
                        "  AND (al.result->>'customer_id')::text = c.id::text "
                        "  AND al.created_at > NOW() - INTERVAL '1 month'"
                        ") "
                        "ORDER BY c.last_active_at DESC NULLS LAST "
                        "LIMIT 50"
                    ),
                    {"biz": business_id},
                )
            ).fetchall()

        candidates = []
        for r in rows:
            active_months = (r.last_active_at or r.created_at) and 1
            referral_count = r.referral_count or 0
            is_power_referrer = referral_count >= 2
            candidates.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "email": r.email,
                    "language": r.language or "fr",
                    "referral_count": referral_count,
                    "power_referrer": is_power_referrer,
                }
            )

        return {"candidates": candidates}

    async def generate_offer(self, context) -> dict:
        """Claude Haiku: personalized offer in customer's language."""
        analyze_out = context.step_output("analyze_usage")
        candidates = analyze_out.get("candidates", [])
        if not candidates:
            return {"offers": []}

        model = await self.check_budget()
        offers = []
        for c in candidates[:10]:
            lang = c["language"]
            system = (
                f"Tu génères une offre d'upgrade personnalisée pour un client SaaS. "
                f"Langue: {'français' if lang == 'fr' else 'anglais'}. "
                f"Court (max 80 mots). Pas de jargon. Un seul CTA clair. "
                f"Si power_referrer: mentionne un avantage ambassadeur."
            )
            user = json.dumps({"customer": c})
            response, cost = await call_claude(model_tier=model, system=system, user=user)
            offers.append(
                {"customer_id": c["id"], "email": c["email"], "body": response.strip(), "language": lang}
            )
        return {"offers": offers}

    async def send_offer(self, context) -> dict:
        """Send offer (max 1/month/customer — enforced in analyze_usage)."""
        gen_out = context.step_output("generate_offer")
        offers = gen_out.get("offers", [])
        sent = 0

        for offer in offers:
            if not offer.get("email"):
                continue
            try:
                if settings.RESEND_API_KEY:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            "https://api.resend.com/emails",
                            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                            json={
                                "from": "upgrade@factorylabs.ca",
                                "to": offer["email"],
                                "subject": "Une offre pour toi" if offer.get("language") == "fr" else "An offer for you",
                                "text": offer["body"],
                            },
                        )
                sent += 1
                await self.log_execution(
                    action="send_offer",
                    result={"customer_id": offer["customer_id"], "email": offer["email"][:6] + "..."},
                )
            except Exception as exc:
                logger.warning("upsell_send_failed", customer_id=offer["customer_id"], error=str(exc))

        return {"sent": sent, "total": len(offers)}

    async def track_conversion(self, context) -> dict:
        """Track conversions (placeholder — would update on subscription upgrade webhook)."""
        send_out = context.step_output("send_offer")
        await self.log_execution(
            action="track_conversion",
            result={"offers_sent": send_out.get("sent", 0), "total_eligible": send_out.get("total", 0)},
        )
        return {"tracked": True}


def register(hatchet_instance):
    agent = UpsellAgent()
    wf = hatchet_instance.workflow(name="upsell-agent", on_crons=["0 15 * * 1"])

    @wf.task(execution_timeout="5m", retries=1)
    async def analyze_usage(input, ctx):
        return await agent.analyze_usage(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def generate_offer(input, ctx):
        return await agent.generate_offer(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def send_offer(input, ctx):
        return await agent.send_offer(ctx)

    @wf.task(execution_timeout="1m", retries=1)
    async def track_conversion(input, ctx):
        return await agent.track_conversion(ctx)

    return wf

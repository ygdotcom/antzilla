"""Agent 13: Email Nurture.

Event-driven (signup, inactivity, churn) + cron for newsletters.
Sequences: onboarding (6 emails/30 days), newsletter (bi-weekly),
re-engagement (14+ days inactive), post-churn (30/90 day win-back).
Frequency cap: max 3 emails/week per user across ALL agents.
"""

from __future__ import annotations

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

MAX_EMAILS_PER_WEEK = 3

SEQUENCES = {
    "onboarding": {"emails": 6, "days": 30, "description": "6 emails over 30 days"},
    "newsletter": {"emails": 1, "days": 14, "description": "bi-weekly"},
    "re_engagement": {"emails": 3, "days": 21, "description": "14+ days inactive"},
    "post_churn": {"emails": 2, "days": 90, "description": "30/90 day win-back"},
}

EMAIL_GENERATION_PROMPT = """\
Tu génères un email de nurture pour un client SaaS canadien.

Tu reçois: le type de séquence, l'étape, le nom du client, la langue, le contexte business.

RÈGLES:
- Ton professionnel mais chaleureux
- Bilingue selon la langue du client (FR québécois ou EN canadien)
- Max 150 mots
- Un seul CTA clair
- Lien de désinscription obligatoire (CASL)

Réponds en JSON: {"subject": "...", "body": "..."}
"""


async def _count_emails_last_7_days(customer_id: int) -> int:
    """Count emails sent to this customer in the last 7 days across ALL agents."""
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT COUNT(*) AS cnt FROM agent_logs "
                    "WHERE action = 'email_sent' "
                    "AND (result->>'customer_id')::text = :cid "
                    "AND created_at > NOW() - INTERVAL '7 days'"
                ),
                {"cid": str(customer_id)},
            )
        ).fetchone()
    return row.cnt if row else 0


class EmailNurture(BaseAgent):
    """Email nurture sequences — onboarding, newsletter, re-engagement, post-churn."""

    agent_name = "email_nurture"
    default_model = "haiku"

    async def _query_recipients_for_type(self, sequence_type: str, businesses: list[dict]) -> list[dict]:
        """Query customers for a single sequence type across businesses."""
        recipients = []
        for biz in businesses:
            async with SessionLocal() as db:
                if sequence_type == "onboarding":
                    rows = (
                        await db.execute(
                            text(
                                "SELECT c.id, c.name, c.email, c.language, c.created_at "
                                "FROM customers c "
                                "WHERE c.business_id = :biz AND c.status IN ('trial', 'active') "
                                "AND c.created_at > NOW() - INTERVAL '30 days' "
                                "ORDER BY c.created_at DESC LIMIT 50"
                            ),
                            {"biz": biz["id"]},
                        )
                    ).fetchall()
                elif sequence_type == "re_engagement":
                    rows = (
                        await db.execute(
                            text(
                                "SELECT c.id, c.name, c.email, c.language, c.last_active_at "
                                "FROM customers c "
                                "WHERE c.business_id = :biz AND c.status IN ('trial', 'active') "
                                "AND (c.last_active_at < NOW() - INTERVAL '14 days' OR c.last_active_at IS NULL) "
                                "LIMIT 50"
                            ),
                            {"biz": biz["id"]},
                        )
                    ).fetchall()
                elif sequence_type == "post_churn":
                    rows = (
                        await db.execute(
                            text(
                                "SELECT c.id, c.name, c.email, c.language "
                                "FROM customers c "
                                "WHERE c.business_id = :biz AND c.status = 'churned' "
                                "AND (c.last_active_at < NOW() - INTERVAL '30 days' OR c.last_active_at IS NULL) "
                                "LIMIT 50"
                            ),
                            {"biz": biz["id"]},
                        )
                    ).fetchall()
                else:
                    rows = (
                        await db.execute(
                            text(
                                "SELECT c.id, c.name, c.email, c.language "
                                "FROM customers c "
                                "WHERE c.business_id = :biz AND c.status IN ('trial', 'active') "
                                "LIMIT 100"
                            ),
                            {"biz": biz["id"]},
                        )
                    ).fetchall()

                for r in rows:
                    recipients.append({
                        "id": r.id,
                        "name": r.name or "",
                        "email": r.email,
                        "language": r.language or "fr",
                        "business_id": biz["id"],
                        "business_name": biz["name"],
                        "sequence_type": sequence_type,
                    })
        return recipients

    async def identify_recipients(self, context) -> dict:
        """Query customers by sequence type. From cron (no input), process ALL types."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        sequence_type = input_data.get("sequence_type")
        businesses = await get_active_businesses()
        if not businesses:
            return {"recipients": [], "sequence_type": sequence_type or "all"}

        if sequence_type:
            # Explicit type from event trigger
            recipients = await self._query_recipients_for_type(sequence_type, businesses)
        else:
            # Cron trigger: process ALL sequence types
            recipients = []
            seen_ids: set[int] = set()
            for st in SEQUENCES:
                for r in await self._query_recipients_for_type(st, businesses):
                    if r["id"] not in seen_ids:
                        recipients.append(r)
                        seen_ids.add(r["id"])
            sequence_type = "all"

        await self.log_execution(
            action="identify_recipients",
            result={"count": len(recipients), "sequence_type": sequence_type},
        )
        return {"recipients": recipients, "sequence_type": sequence_type}

    async def generate_email(self, context) -> dict:
        """Claude Haiku generates email in customer's language."""
        identify_out = context.step_output("identify_recipients")
        recipients = identify_out.get("recipients", [])
        sequence_type = identify_out.get("sequence_type", "newsletter")

        if not recipients:
            return {"emails": [], "skipped": 0}

        playbook = await load_playbook(recipients[0]["business_id"]) if recipients else {}
        messaging = playbook.get("messaging", {}) if playbook else {}

        emails = []
        total_cost = 0.0
        for rec in recipients[:20]:
            model_tier = await self.check_budget()
            rec_sequence = rec.get("sequence_type", sequence_type)
            user_prompt = json.dumps({
                "sequence_type": rec_sequence,
                "customer_name": rec["name"],
                "language": rec["language"],
                "business_name": rec["business_name"],
                "messaging": messaging,
            }, default=str)

            response, cost = await call_claude(
                model_tier=model_tier,
                system=EMAIL_GENERATION_PROMPT,
                user=user_prompt,
                max_tokens=512,
                temperature=0.5,
            )
            total_cost += cost

            try:
                msg = json.loads(response)
            except json.JSONDecodeError:
                msg = {"subject": "Newsletter", "body": response[:500]}

            emails.append({
                "customer_id": rec["id"],
                "email": rec["email"],
                "name": rec["name"],
                "business_id": rec["business_id"],
                "subject": msg.get("subject", ""),
                "body": msg.get("body", ""),
            })

        await self.log_execution(
            action="generate_email",
            result={"generated": len(emails)},
            cost_usd=total_cost,
        )
        return {"emails": emails}

    async def check_frequency_cap(self, context) -> dict:
        """Filter out recipients who would exceed max 3 emails/week."""
        gen_out = context.step_output("generate_email")
        emails = gen_out.get("emails", [])
        allowed = []

        for e in emails:
            count = await _count_emails_last_7_days(e["customer_id"])
            if count < MAX_EMAILS_PER_WEEK:
                allowed.append(e)
            else:
                logger.info("frequency_cap_skipped", customer_id=e["customer_id"], count=count)

        await self.log_execution(
            action="check_frequency_cap",
            result={"allowed": len(allowed), "skipped": len(emails) - len(allowed)},
        )
        return {"emails": allowed}

    async def send_email(self, context) -> dict:
        """Send via Resend."""
        cap_out = context.step_output("check_frequency_cap")
        emails = cap_out.get("emails", [])

        if not settings.RESEND_API_KEY:
            logger.warning("send_email_skipped", reason="no_resend_api_key")
            return {"sent": 0}

        sent = 0
        for e in emails:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                        json={
                            "from": "nurture@factorylabs.ca",
                            "to": e["email"],
                            "subject": e["subject"],
                            "text": e["body"],
                        },
                    )
                sent += 1
                await self.log_execution(
                    action="email_sent",
                    result={"customer_id": e["customer_id"]},
                    business_id=e["business_id"],
                )
            except Exception as exc:
                logger.warning("send_email_failed", email=e["email"][:10] + "...", error=str(exc))

        return {"sent": sent}

    async def log(self, context) -> dict:
        """Final logging step."""
        send_out = context.step_output("send_email")
        sent = send_out.get("sent", 0)
        await self.log_execution(
            action="email_nurture_run",
            result={"emails_sent": sent},
        )
        return {"emails_sent": sent}


def register(hatchet_instance):
    agent = EmailNurture()
    wf = hatchet_instance.workflow(name="email-nurture", on_crons=["0 14 * * 1,4"])

    @wf.task(execution_timeout="5m", retries=1)
    async def identify_recipients(input, ctx):
        return await agent.identify_recipients(ctx)

    @wf.task(execution_timeout="8m", retries=1)
    async def generate_email(input, ctx):
        return await agent.generate_email(ctx)

    @wf.task(execution_timeout="2m", retries=1)
    async def check_frequency_cap(input, ctx):
        return await agent.check_frequency_cap(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def send_email(input, ctx):
        return await agent.send_email(ctx)

    @wf.task(execution_timeout="1m", retries=1)
    async def log(input, ctx):
        return await agent.log(ctx)

    return wf

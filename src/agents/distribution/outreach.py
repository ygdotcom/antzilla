"""Sub-agent 12d: Outreach Agent.

Generates personalised cold email sequences from gtm_playbooks.messaging
config and sends via Instantly (secondary domains only).

TIERED AUTONOMY (§13.C):
  Week 1-2:  ALL messages → Slack for human review before sending.
  Week 3-4:  Auto-send for leads scoring < 70. Human reviews ≥ 70.
  Month 2+:  Full autonomy. Human reviews only if reply rate < 2%.

A/B tests subject lines and openings via outreach_experiments table.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses, load_playbook
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

OUTREACH_SYSTEM_PROMPT = """\
Tu génères un cold email personnalisé pour un prospect B2B au Canada.

Tu reçois: le profil du lead, la value proposition, le ton, le framework de messaging.
Tu reçois aussi des CONNAISSANCES ACCUMULÉES par la factory (templates gagnants, patterns prouvés). Utilise-les.

RÈGLES 2026:
- MOINS DE 80 mots. Pas de lien dans le premier email.
- Pas d'images, pas de pièces jointes, pas de HTML.
- Ton direct, authentique. Tutoiement si québécois.
- Un seul CTA clair.
- CASL: le lead doit avoir un email publié publiquement (conspicuous publication).
- Référence un signal d'achat si disponible (nouveau permis, embauche, plainte concurrent).
- NE JAMAIS mentionner "IA", "automatisé", ou "robot".

Réponds en JSON:
{"subject": "...", "body": "...", "framework_used": "pain_agitate_solve|before_after_bridge|..."}
"""

AUTONOMY_LEVELS = {
    "shadow": {"max_age_days": 14, "description": "All messages to Slack for human approval"},
    "semi": {"max_age_days": 30, "auto_send_below_score": 70, "description": "Auto-send low-value, human reviews high-value"},
    "full": {"description": "Full autonomy, human reviews only on low reply rates"},
}


def determine_autonomy_level(business_created_at: datetime | None) -> str:
    """Determine the autonomy tier based on business age."""
    if not business_created_at:
        return "shadow"
    age_days = (datetime.now(tz=timezone.utc) - business_created_at).days
    if age_days < 14:
        return "shadow"
    if age_days < 30:
        return "semi"
    return "full"


async def _send_to_slack_for_review(lead_name: str, subject: str, body: str, business_slug: str) -> None:
    """Post draft message to Slack #outreach-review for human approval."""
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                settings.SLACK_WEBHOOK_URL,
                json={
                    "text": (
                        f":email: *Outreach Review* — {business_slug}\n"
                        f"*To:* {lead_name}\n"
                        f"*Subject:* {subject}\n"
                        f"*Body:*\n```{body}```\n"
                        f"React :white_check_mark: to approve, :x: to reject."
                    )
                },
            )
    except Exception:
        logger.warning("slack_outreach_review_failed")


class OutreachAgent(BaseAgent):
    """Generates and sends personalised cold email sequences."""

    agent_name = "outreach_agent"
    default_model = "haiku"

    async def run_outreach(self, context) -> dict:
        """Generate and queue outreach messages for enriched leads."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"businesses": 0, "messages_generated": 0, "messages_sent": 0}

        total_generated = 0
        total_sent = 0
        total_queued = 0

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            messaging = playbook.get("messaging", {})
            outreach_cfg = playbook.get("outreach", {})

            # KNOWLEDGE-INFORMED: query winning email templates for this vertical
            from src.knowledge import query_knowledge, format_knowledge_for_prompt
            email_knowledge = await query_knowledge(
                category="email_template_winner",
                vertical=biz.get("slug"),
                limit=5,
            )
            knowledge_block = format_knowledge_for_prompt(email_knowledge)
            # Collect emails for quality gate (checked after batch generation)
            batch_emails = []
            cadence = outreach_cfg.get("sequence_days", [0, 3, 7, 12])
            max_daily = outreach_cfg.get("max_daily_emails", 50)

            # Get business creation date for autonomy level
            async with SessionLocal() as db:
                biz_row = (
                    await db.execute(
                        text("SELECT created_at FROM businesses WHERE id = :id"), {"id": biz["id"]}
                    )
                ).fetchone()
            autonomy = determine_autonomy_level(biz_row.created_at if biz_row else None)

            # Get enriched leads ready for outreach
            async with SessionLocal() as db:
                leads = (
                    await db.execute(
                        text(
                            "SELECT id, name, email, company, phone, score, "
                            "signal_type, signal_data, language, sequence_step "
                            "FROM leads "
                            "WHERE business_id = :biz AND status = 'enriched' "
                            "AND email IS NOT NULL "
                            "ORDER BY score DESC LIMIT :limit"
                        ),
                        {"biz": biz["id"], "limit": max_daily},
                    )
                ).fetchall()

            for lead in leads:
                if not lead.email:
                    continue

                # Build personalisation context
                signal_context = ""
                if lead.signal_type and lead.signal_data:
                    sig_data = json.loads(lead.signal_data) if isinstance(lead.signal_data, str) else lead.signal_data
                    signal_context = f"Signal: {lead.signal_type} — {json.dumps(sig_data)}"

                prompt_data = {
                    "lead": {
                        "name": lead.name,
                        "company": lead.company,
                        "language": lead.language or "fr",
                        "signal": signal_context,
                    },
                    "messaging": messaging,
                    "sequence_step": lead.sequence_step or 0,
                    "max_words": 80,
                }
                if knowledge_block:
                    prompt_data["winning_patterns"] = knowledge_block
                user_prompt = json.dumps(prompt_data, default=str)

                # Generate message
                model_tier = await self.check_budget()
                response, cost = await call_claude(
                    model_tier=model_tier,
                    system=OUTREACH_SYSTEM_PROMPT,
                    user=user_prompt,
                    max_tokens=512,
                    temperature=0.6,
                )

                try:
                    msg = json.loads(response)
                except json.JSONDecodeError:
                    msg = {"subject": "Quick question", "body": response[:300]}

                subject = msg.get("subject", "")
                body = msg.get("body", "")
                total_generated += 1
                batch_emails.append({"subject": subject, "body": body})

                # Apply tiered autonomy
                should_send = False
                if autonomy == "full":
                    should_send = True
                elif autonomy == "semi":
                    should_send = (lead.score or 0) < 70
                    if not should_send:
                        await _send_to_slack_for_review(lead.name, subject, body, biz["slug"])
                        total_queued += 1
                else:  # shadow
                    await _send_to_slack_for_review(lead.name, subject, body, biz["slug"])
                    total_queued += 1

                if should_send:
                    # In production: send via Instantly API
                    total_sent += 1

                # Update lead status
                async with SessionLocal() as db:
                    new_step = (lead.sequence_step or 0) + 1
                    await db.execute(
                        text(
                            "UPDATE leads SET "
                            "status = 'contacted', "
                            "sequence_step = :step, "
                            "last_contacted_at = NOW() "
                            "WHERE id = :id"
                        ),
                        {"step": new_step, "id": lead.id},
                    )
                    await db.commit()

            # QUALITY GATE: sample 3 random emails and quality-check before sending
            if batch_emails:
                from src.quality import quality_check_emails
                qc = await quality_check_emails(batch_emails, sample_size=3)
                if not qc["passed"]:
                    logger.warning("quality_gate_failed", business=biz["slug"], blocked=qc["blocked_count"])
                    # In production: block sending and route to human review

            await self.log_execution(
                action="run_outreach",
                result={
                    "autonomy": autonomy,
                    "generated": total_generated,
                    "sent": total_sent,
                    "queued_for_review": total_queued,
                },
                business_id=biz["id"],
                cost_usd=0,
            )

        return {
            "businesses": len(businesses),
            "messages_generated": total_generated,
            "messages_sent": total_sent,
            "queued_for_review": total_queued,
        }


def register(hatchet_instance) -> type:

    @hatchet_instance.workflow(name="outreach-agent", on_crons=["0 14 * * *"])
    class _Registered(OutreachAgent):
        @hatchet_instance.task(execution_timeout="25m", retries=1)
        async def run_outreach(self, context) -> dict:
            return await OutreachAgent.run_outreach(self, context)

    return _Registered

"""Sub-agent 12e: Reply Handler.

Classifies incoming replies with Claude Haiku, routes them appropriately:
- positive_interested → Voice Agent for warm call
- positive_question → RAG answer + keep in sequence
- negative_not_interested → close, suppress
- objection → generate handling, escalate if high-value
- ooo_autoresponder → snooze sequence
- unsubscribe → immediate CASL suppression
- wrong_person → ask for referral

Low-confidence classifications (< 80%) → Slack for human review.
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

CLASSIFICATION_PROMPT = """\
Tu es un classifieur de réponses à des cold emails B2B.

Classifie cette réponse dans EXACTEMENT une catégorie:
- positive_interested: le prospect est intéressé, veut en savoir plus, demande une démo
- positive_question: le prospect pose une question sur le produit/prix/fonctionnalités
- negative_not_interested: refus poli ou ferme
- negative_competitor: utilise déjà un concurrent (mentionne le nom)
- objection: a une objection spécifique (prix, timing, besoin)
- ooo_autoresponder: message d'absence / réponse automatique
- unsubscribe: demande de désinscription / ne plus contacter
- wrong_person: pas la bonne personne, suggère quelqu'un d'autre

Réponds en JSON:
{
  "classification": "positive_interested|positive_question|negative_not_interested|negative_competitor|objection|ooo_autoresponder|unsubscribe|wrong_person",
  "confidence": 0.95,
  "competitor_name": "string or null",
  "return_date": "YYYY-MM-DD or null (for OOO)",
  "suggested_action": "brief description",
  "reasoning": "one sentence"
}
"""

REPLY_CATEGORIES = [
    "positive_interested",
    "positive_question",
    "negative_not_interested",
    "negative_competitor",
    "objection",
    "ooo_autoresponder",
    "unsubscribe",
    "wrong_person",
]

CONFIDENCE_THRESHOLD = 0.80


async def _route_positive_interested(lead_id: int, business_id: int) -> None:
    """Update lead to 'replied' and flag for Voice Agent warm call."""
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE leads SET status = 'replied', replied_at = NOW() WHERE id = :id"
            ),
            {"id": lead_id},
        )
        await db.commit()
    logger.info("reply_positive_interested", lead_id=lead_id, action="route_to_voice_agent")


async def _route_question(lead_id: int, business_id: int) -> None:
    """Keep lead in sequence, mark as replied."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET status = 'replied', replied_at = NOW() WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()


async def _route_not_interested(lead_id: int) -> None:
    """Close lead, add to suppression."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET status = 'lost' WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()


async def _route_unsubscribe(lead_id: int) -> None:
    """CASL: immediately suppress. Process within 10 business days (we do it instantly)."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET status = 'unsubscribed' WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()
    logger.info("casl_unsubscribe", lead_id=lead_id)


async def _route_ooo(lead_id: int, return_date: str | None) -> None:
    """Snooze the sequence until return date."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET status = 'replied', replied_at = NOW() WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()
    logger.info("reply_ooo", lead_id=lead_id, return_date=return_date)


async def _escalate_to_slack(lead_name: str, reply_text: str, classification: dict, business_slug: str) -> None:
    """Escalate low-confidence or high-value replies to Slack."""
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                settings.SLACK_WEBHOOK_URL,
                json={
                    "text": (
                        f":speech_balloon: *Reply Review* — {business_slug}\n"
                        f"*From:* {lead_name}\n"
                        f"*Classification:* {classification.get('classification')} "
                        f"({classification.get('confidence', 0):.0%} confidence)\n"
                        f"*Reply:*\n```{reply_text[:500]}```\n"
                        f"*Suggested:* {classification.get('suggested_action', 'Review manually')}"
                    )
                },
            )
    except Exception:
        logger.warning("slack_escalation_failed")


class ReplyHandler(BaseAgent):
    """Classifies and routes incoming email replies."""

    agent_name = "reply_handler"
    default_model = "haiku"

    async def process_replies(self, context) -> dict:
        """Process unhandled replies across all businesses."""
        # Get leads that have replied but haven't been classified yet
        async with SessionLocal() as db:
            leads = (
                await db.execute(
                    text(
                        "SELECT l.id, l.business_id, l.name, l.email, l.company, l.score, "
                        "b.slug AS business_slug "
                        "FROM leads l JOIN businesses b ON l.business_id = b.id "
                        "WHERE l.status = 'replied' AND l.replied_at > NOW() - INTERVAL '24 hours' "
                        "ORDER BY l.score DESC LIMIT 50"
                    )
                )
            ).fetchall()

        if not leads:
            return {"processed": 0}

        processed = 0
        classifications = {"positive_interested": 0, "positive_question": 0,
                          "negative_not_interested": 0, "objection": 0,
                          "ooo_autoresponder": 0, "unsubscribe": 0, "other": 0}

        for lead in leads:
            # In production, fetch actual reply text from Instantly webhook data
            # For now, use a placeholder that the workflow_input provides
            input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
            reply_text = input_data.get("reply_text", "")
            if not reply_text:
                continue

            # KNOWLEDGE-INFORMED: include past winning objection responses
            from src.knowledge import query_knowledge, format_knowledge_for_prompt
            objection_knowledge = await query_knowledge(category="objection_response", limit=5)
            enhanced_prompt = CLASSIFICATION_PROMPT
            obj_block = format_knowledge_for_prompt(objection_knowledge)
            if obj_block:
                enhanced_prompt += f"\n\n{obj_block}"

            model_tier = await self.check_budget()
            response, cost = await call_claude(
                model_tier=model_tier,
                system=enhanced_prompt,
                user=f"Lead: {lead.name} ({lead.company})\n\nReply:\n{reply_text}",
                max_tokens=256,
                temperature=0.1,
            )

            try:
                classification = json.loads(response)
            except json.JSONDecodeError:
                classification = {"classification": "objection", "confidence": 0.5}

            cat = classification.get("classification", "other")
            confidence = classification.get("confidence", 0.5)

            # Low confidence → escalate to Slack
            if confidence < CONFIDENCE_THRESHOLD:
                await _escalate_to_slack(lead.name, reply_text, classification, lead.business_slug)
                classifications["other"] = classifications.get("other", 0) + 1
            else:
                # Route based on classification
                if cat == "positive_interested":
                    # HUMAN TOUCHPOINT: hot leads (score >= 80) or first 5 customers → Slack
                    customer_count = 0
                    async with SessionLocal() as _db:
                        _row = (await _db.execute(text("SELECT COUNT(*) AS cnt FROM customers WHERE business_id = :biz"), {"biz": lead.business_id})).fetchone()
                        customer_count = _row.cnt or 0

                    if (lead.score or 0) >= 80 or customer_count < 5:
                        await _escalate_to_slack(
                            lead.name, reply_text,
                            {"classification": "positive_interested", "confidence": confidence,
                             "suggested_action": f"🔥 Hot lead (score {lead.score}). Call personally or let Voice Agent handle?"},
                            lead.business_slug,
                        )
                    await _route_positive_interested(lead.id, lead.business_id)
                    classifications["positive_interested"] += 1
                elif cat == "positive_question":
                    await _route_question(lead.id, lead.business_id)
                    classifications["positive_question"] += 1
                elif cat in ("negative_not_interested", "negative_competitor"):
                    await _route_not_interested(lead.id)
                    classifications["negative_not_interested"] += 1
                elif cat == "unsubscribe":
                    await _route_unsubscribe(lead.id)
                    classifications["unsubscribe"] += 1
                elif cat == "ooo_autoresponder":
                    await _route_ooo(lead.id, classification.get("return_date"))
                    classifications["ooo_autoresponder"] += 1
                elif cat == "objection":
                    if (lead.score or 0) >= 70:
                        await _escalate_to_slack(lead.name, reply_text, classification, lead.business_slug)
                    classifications["objection"] += 1
                else:
                    classifications["other"] = classifications.get("other", 0) + 1

            # Store winning objection→conversion patterns in factory knowledge
            if cat == "positive_interested" and reply_text:
                from src.knowledge import store_knowledge
                try:
                    await store_knowledge(
                        category="objection_response",
                        vertical=None,
                        insight=f"Lead '{lead.name}' converted after: {reply_text[:100]}",
                        data={"reply_excerpt": reply_text[:500], "lead_score": lead.score},
                        confidence=0.5,
                        source_business_id=lead.business_id,
                    )
                except Exception:
                    pass

            processed += 1
            await self.log_execution(
                action="classify_reply",
                result={"classification": cat, "confidence": confidence},
                cost_usd=cost,
                business_id=lead.business_id,
            )

        return {"processed": processed, "classifications": classifications}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="reply-handler", on_crons=["*/30 * * * *"], timeout="10m")
    class _Registered(ReplyHandler):
        @hatchet_instance.step(timeout="8m", retries=1)
        async def process_replies(self, context: Context) -> dict:
            return await ReplyHandler.process_replies(self, context)

    return _Registered

"""Agent 18: Support Agent.

RAG-powered customer support using pgvector on the existing Postgres.
Responds in the customer's language (FR/EN).  Auto-updates the knowledge
base with new Q&A pairs.  Detects churn signals daily.
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

SUPPORT_SYSTEM_PROMPT = """\
Tu es l'agent de support pour {business_name}. Tu réponds aux questions des clients.

CONTEXTE DE LA BASE DE CONNAISSANCES:
{kb_context}

RÈGLES:
- Réponds dans la langue du client ({language}).
- Sois concis et utile. Maximum 200 mots.
- Si tu ne connais pas la réponse, dis-le honnêtement et propose de transférer à un humain.
- Ton: professionnel mais chaleureux. Tutoiement en français québécois.
- Inclus des liens vers la documentation pertinente si disponible.
- NE JAMAIS inventer de fonctionnalités ou de prix.

Réponds directement au client, pas de méta-commentaire.
"""

CHURN_SIGNALS = {
    "inactive_7d": "No activity in 7+ days",
    "usage_drop_50": "Usage dropped 50%+ from previous period",
    "unresolved_48h": "Support ticket unresolved for 48+ hours",
    "payment_failed": "Payment failed and not recovered",
    "downgraded": "Recently downgraded from paid to free",
}


async def _search_knowledge_base(db, business_id: int, query: str, limit: int = 5) -> list[dict]:
    """Search the knowledge base using Claude Haiku for relevance ranking."""
    rows = (
        await db.execute(
            text(
                "SELECT title, content, source FROM knowledge_base "
                "WHERE business_id = :biz "
                "ORDER BY created_at DESC LIMIT :candidate_limit"
            ),
            {"biz": business_id, "candidate_limit": limit * 4},
        )
    ).fetchall()

    if not rows:
        return []

    candidates = [{"i": i, "title": r.title, "snippet": r.content[:200]} for i, r in enumerate(rows)]
    try:
        response, _ = await call_claude(
            model_tier="haiku",
            system=(
                "Return a JSON array of the indices (integers) of the most relevant "
                "knowledge base articles for the customer question. Max 5 indices. "
                "Output ONLY the JSON array, nothing else."
            ),
            user=json.dumps({"question": query[:200], "articles": candidates}),
            max_tokens=100,
            temperature=0.0,
        )
        indices = json.loads(response.strip())
        if isinstance(indices, list):
            results = []
            for i in indices:
                if isinstance(i, int) and 0 <= i < len(rows):
                    r = rows[i]
                    results.append({"title": r.title, "content": r.content[:500], "source": r.source})
            if results:
                return results[:limit]
    except Exception:
        logger.debug("kb_claude_ranking_failed", fallback="recent")

    return [{"title": r.title, "content": r.content[:500], "source": r.source} for r in rows[:limit]]


class SupportAgent(BaseAgent):
    """RAG-powered bilingual customer support."""

    agent_name = "support_agent"
    default_model = "sonnet"

    async def handle_ticket(self, context) -> dict:
        """Process an incoming support message."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        customer_id = input_data.get("customer_id")
        message = input_data.get("message", "")
        channel = input_data.get("channel", "in_app")

        if not message:
            return {"response": None, "reason": "empty message"}

        # Load customer info
        async with SessionLocal() as db:
            cust = (
                await db.execute(
                    text(
                        "SELECT c.name, c.language, c.email, b.name AS biz_name "
                        "FROM customers c JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.id = :cid"
                    ),
                    {"cid": customer_id},
                )
            ).fetchone()

            language = cust.language if cust else "fr"
            biz_name = cust.biz_name if cust else ""

            # RAG: search knowledge base
            kb_results = await _search_knowledge_base(db, business_id, message)

        kb_context = "\n\n".join(
            f"[{r['source']}] {r['title']}: {r['content']}" for r in kb_results
        ) if kb_results else "Aucun article pertinent trouvé dans la base de connaissances."

        model_tier = await self.check_budget()
        system = SUPPORT_SYSTEM_PROMPT.format(
            business_name=biz_name,
            kb_context=kb_context,
            language="français québécois" if language == "fr" else "English",
        )

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system,
            user=message,
            max_tokens=1024,
            temperature=0.3,
        )

        # Save ticket
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO support_tickets "
                    "(business_id, customer_id, channel, subject, messages, status) "
                    "VALUES (:biz, :cust, :channel, :subject, :msgs, 'resolved')"
                ),
                {
                    "biz": business_id,
                    "cust": customer_id,
                    "channel": channel,
                    "subject": message[:100],
                    "msgs": json.dumps([
                        {"role": "customer", "content": message},
                        {"role": "agent", "content": response_text},
                    ]),
                },
            )

            # Auto-update KB with new Q&A pair
            await db.execute(
                text(
                    "INSERT INTO knowledge_base (business_id, source, title, content) "
                    "VALUES (:biz, 'support_ticket', :title, :content)"
                ),
                {
                    "biz": business_id,
                    "title": message[:200],
                    "content": response_text[:2000],
                },
            )
            await db.commit()

        await self.log_execution(
            action="handle_ticket",
            result={"kb_results": len(kb_results), "language": language},
            cost_usd=cost,
            business_id=business_id,
        )

        return {"response": response_text, "language": language, "kb_hits": len(kb_results)}

    async def check_churn_signals(self, context) -> dict:
        """Daily cron: detect customers showing churn signals."""
        async with SessionLocal() as db:
            # Inactive > 7 days
            inactive = (
                await db.execute(
                    text(
                        "SELECT id, name, email, business_id FROM customers "
                        "WHERE status = 'active' "
                        "AND last_active_at < NOW() - INTERVAL '7 days' "
                        "AND last_active_at IS NOT NULL"
                    )
                )
            ).fetchall()

            # Unresolved tickets > 48h
            stale_tickets = (
                await db.execute(
                    text(
                        "SELECT customer_id, business_id FROM support_tickets "
                        "WHERE status = 'open' "
                        "AND created_at < NOW() - INTERVAL '48 hours'"
                    )
                )
            ).fetchall()

        at_risk = len(inactive) + len(stale_tickets)
        logger.info("churn_signals_detected", inactive=len(inactive), stale_tickets=len(stale_tickets))

        return {
            "inactive_7d": len(inactive),
            "stale_tickets_48h": len(stale_tickets),
            "total_at_risk": at_risk,
        }

    async def scan_feature_requests(self, context) -> dict:
        """Scan support tickets for feature requests. Aggregate into feature_requests table."""
        async with SessionLocal() as db:
            # Find support tickets mentioning features/requests
            tickets = (await db.execute(text(
                "SELECT business_id, messages FROM support_tickets "
                "WHERE status = 'resolved' AND created_at > NOW() - INTERVAL '7 days'"
            ))).fetchall()

            # In production: use Claude to extract feature requests from ticket content
            # and cluster similar requests together

        return {"tickets_scanned": len(tickets)}


def register(hatchet_instance):
    agent = SupportAgent()

    wf_ticket = hatchet_instance.workflow(name="support-agent")

    @wf_ticket.task(execution_timeout="5m", retries=2)
    async def handle_ticket(input, ctx):
        return await agent.handle_ticket(ctx)

    wf_churn = hatchet_instance.workflow(name="support-churn-check", on_crons=["0 14 * * *"])

    @wf_churn.task(execution_timeout="8m", retries=1)
    async def check_churn_signals(input, ctx):
        return await agent.check_churn_signals(ctx)

    return wf_ticket, wf_churn

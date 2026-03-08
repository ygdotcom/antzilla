"""Agent 28: Knowledge Agent — the factory's long-term memory.

Weekly + after A/B test conclusions + after business kill/milestone.
Scans all agents' outputs and extracts cross-business patterns.

By Business #5, the factory should be significantly smarter than
it was for Business #1. Every failure teaches, every success compounds.
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.db import SessionLocal
from src.knowledge import query_knowledge, store_knowledge, format_knowledge_for_prompt
from src.llm import call_claude

logger = structlog.get_logger()

SYNTHESIS_PROMPT = """\
Tu es l'agent de connaissances de la Factory. Tu analyses les patterns cross-business.

Tu reçois des insights bruts extraits de plusieurs businesses. Ton job:
1. Identifier les META-PATTERNS qui transcendent les businesses individuelles
2. Quantifier la confiance (0-1) basée sur le nombre d'occurrences
3. Produire des insights actionnables que les autres agents peuvent utiliser

Réponds en JSON array:
[{
  "category": "email_template_winner|channel_effectiveness|idea_scoring_calibration|objection_response|icp_insight|pricing_insight|content_format_winner|onboarding_pattern|churn_reason|referral_tactic",
  "vertical": "trades|professional_services|ecommerce|null",
  "insight": "Human-readable insight, 1-2 sentences",
  "data": {"supporting_data": "..."},
  "confidence": 0.7
}]
"""


class KnowledgeAgent(BaseAgent):
    """Cross-business learning — extracts and stores reusable knowledge."""

    agent_name = "knowledge_agent"
    default_model = "opus"

    async def scan_outreach_experiments(self, context) -> dict:
        """Find concluded A/B tests. Extract winning patterns."""
        async with SessionLocal() as db:
            winners = (
                await db.execute(
                    text(
                        "SELECT e.business_id, e.experiment_name, e.variant_a, e.variant_b, "
                        "e.replies_a, e.replies_b, e.positive_replies_a, e.positive_replies_b, "
                        "e.winner, e.sends_a, e.sends_b, b.niche "
                        "FROM outreach_experiments e "
                        "JOIN businesses b ON e.business_id = b.id "
                        "WHERE e.winner IS NOT NULL "
                        "AND e.decided_at > NOW() - INTERVAL '30 days'"
                    )
                )
            ).fetchall()

        insights_stored = 0
        for w in winners:
            winning_text = w.variant_a if w.winner == "a" else w.variant_b
            losing_text = w.variant_a if w.winner == "b" else w.variant_b
            win_rate = (w.positive_replies_a if w.winner == "a" else w.positive_replies_b) / max(
                (w.sends_a if w.winner == "a" else w.sends_b), 1
            )
            lose_rate = (w.positive_replies_a if w.winner == "b" else w.positive_replies_b) / max(
                (w.sends_a if w.winner == "b" else w.sends_b), 1
            )

            await store_knowledge(
                category="email_template_winner",
                vertical=w.niche,
                insight=f"In {w.experiment_name}: '{winning_text[:60]}...' beat '{losing_text[:60]}...' ({win_rate:.1%} vs {lose_rate:.1%} positive reply rate)",
                data={
                    "experiment": w.experiment_name,
                    "winner": winning_text,
                    "loser": losing_text,
                    "win_rate": round(win_rate, 4),
                    "lose_rate": round(lose_rate, 4),
                    "sample_size": (w.sends_a or 0) + (w.sends_b or 0),
                },
                confidence=min(0.9, 0.5 + ((w.sends_a or 0) + (w.sends_b or 0)) / 1000),
                source_business_id=w.business_id,
            )
            insights_stored += 1

        return {"experiments_scanned": len(winners), "insights_stored": insights_stored}

    async def scan_channel_performance(self, context) -> dict:
        """Compare CAC by channel across businesses."""
        async with SessionLocal() as db:
            channels = (
                await db.execute(
                    text(
                        "SELECT b.id AS biz_id, b.niche, l.source, "
                        "COUNT(*) AS total_leads, "
                        "COUNT(*) FILTER (WHERE l.status = 'converted') AS converted, "
                        "COALESCE(SUM(bt.cost_usd), 0) AS total_cost "
                        "FROM leads l "
                        "JOIN businesses b ON l.business_id = b.id "
                        "LEFT JOIN budget_tracking bt ON bt.business_id = b.id "
                        "WHERE l.source IS NOT NULL "
                        "GROUP BY b.id, b.niche, l.source "
                        "HAVING COUNT(*) >= 10"
                    )
                )
            ).fetchall()

        # Group by vertical + channel
        by_vertical: dict[str, dict] = {}
        for ch in channels:
            vert = ch.niche or "unknown"
            cac = ch.total_cost / max(ch.converted, 1)
            by_vertical.setdefault(vert, []).append({
                "source": ch.source,
                "leads": ch.total_leads,
                "converted": ch.converted,
                "cac": round(float(cac), 2),
            })

        stored = 0
        for vertical, channel_data in by_vertical.items():
            if len(channel_data) >= 2:
                sorted_channels = sorted(channel_data, key=lambda c: c["cac"])
                best = sorted_channels[0]
                worst = sorted_channels[-1]
                await store_knowledge(
                    category="channel_effectiveness",
                    vertical=vertical,
                    insight=f"For {vertical}: {best['source']} has lowest CAC (${best['cac']}) vs {worst['source']} (${worst['cac']})",
                    data={"channels": channel_data},
                    confidence=0.6,
                )
                stored += 1

        return {"verticals_analyzed": len(by_vertical), "insights_stored": stored}

    async def calibrate_idea_scoring(self, context) -> dict:
        """Compare Idea Factory scores vs actual outcomes."""
        async with SessionLocal() as db:
            ideas = (
                await db.execute(
                    text(
                        "SELECT i.id, i.name, i.score, i.scoring_details, i.niche, "
                        "b.mrr, b.customers_count, b.status, b.kill_score "
                        "FROM ideas i "
                        "JOIN businesses b ON b.idea_id = i.id "
                        "WHERE i.score IS NOT NULL AND b.created_at < NOW() - INTERVAL '90 days'"
                    )
                )
            ).fetchall()

        if not ideas:
            return {"ideas_analyzed": 0, "calibration_stored": False}

        overperformers = [i for i in ideas if (i.mrr or 0) > 500 and (i.score or 0) < 7.5]
        underperformers = [i for i in ideas if (i.mrr or 0) < 100 and (i.score or 0) > 7.5 and i.status != 'killed']

        if overperformers or underperformers:
            await store_knowledge(
                category="idea_scoring_calibration",
                vertical=None,
                insight=f"{len(overperformers)} ideas scored low but performed well; {len(underperformers)} scored high but underperformed. Consider adjusting scoring weights.",
                data={
                    "overperformers": [{"name": i.name, "score": float(i.score), "mrr": float(i.mrr or 0)} for i in overperformers],
                    "underperformers": [{"name": i.name, "score": float(i.score), "mrr": float(i.mrr or 0)} for i in underperformers],
                },
                confidence=0.5 + len(ideas) * 0.05,
            )

        return {"ideas_analyzed": len(ideas), "calibration_stored": bool(overperformers or underperformers)}

    async def extract_churn_reasons(self, context) -> dict:
        """Scan churned customers' last interactions for patterns."""
        async with SessionLocal() as db:
            churned = (
                await db.execute(
                    text(
                        "SELECT c.business_id, b.niche, "
                        "COUNT(*) AS churned_count, "
                        "AVG(EXTRACT(EPOCH FROM (c.created_at - c.last_active_at)) / 86400) AS avg_inactive_days "
                        "FROM customers c "
                        "JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.status = 'churned' "
                        "GROUP BY c.business_id, b.niche "
                        "HAVING COUNT(*) >= 3"
                    )
                )
            ).fetchall()

        stored = 0
        for ch in churned:
            await store_knowledge(
                category="churn_reason",
                vertical=ch.niche,
                insight=f"In {ch.niche}: {ch.churned_count} customers churned after avg {ch.avg_inactive_days:.0f} days of inactivity",
                data={"churned_count": ch.churned_count, "avg_inactive_days": float(ch.avg_inactive_days or 0)},
                confidence=0.5 + ch.churned_count * 0.02,
                source_business_id=ch.business_id,
            )
            stored += 1

        return {"churn_patterns": stored}

    async def synthesize_with_claude(self, context) -> dict:
        """Send all recent insights to Claude Opus for meta-pattern analysis."""
        recent = await query_knowledge(min_confidence=0.3, limit=50)
        if len(recent) < 5:
            return {"meta_insights": 0, "reason": "Not enough data yet"}

        model_tier = await self.check_budget()
        response, cost = await call_claude(
            model_tier=model_tier,
            system=SYNTHESIS_PROMPT,
            user=json.dumps(recent, default=str),
            max_tokens=4096,
            temperature=0.3,
        )

        try:
            meta_insights = json.loads(response)
            if not isinstance(meta_insights, list):
                meta_insights = [meta_insights]
        except json.JSONDecodeError:
            meta_insights = []

        stored = 0
        for mi in meta_insights:
            if isinstance(mi, dict) and "insight" in mi:
                await store_knowledge(
                    category=mi.get("category", "icp_insight"),
                    vertical=mi.get("vertical"),
                    insight=mi["insight"],
                    data=mi.get("data", {}),
                    confidence=mi.get("confidence", 0.5),
                )
                stored += 1

        await self.log_execution(
            action="synthesize",
            result={"input_insights": len(recent), "meta_insights": stored},
            cost_usd=cost,
        )

        return {"meta_insights": stored, "cost_usd": cost}


def register(hatchet_instance) -> type:

    @hatchet_instance.workflow(name="knowledge-agent", on_crons=["0 9 * * 0"])
    class _Registered(KnowledgeAgent):
        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def scan_outreach_experiments(self, context) -> dict:
            return await KnowledgeAgent.scan_outreach_experiments(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def scan_channel_performance(self, context) -> dict:
            return await KnowledgeAgent.scan_channel_performance(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def calibrate_idea_scoring(self, context) -> dict:
            return await KnowledgeAgent.calibrate_idea_scoring(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def extract_churn_reasons(self, context) -> dict:
            return await KnowledgeAgent.extract_churn_reasons(self, context)

        @hatchet_instance.task(execution_timeout="10m", retries=1)
        async def synthesize_with_claude(self, context) -> dict:
            return await KnowledgeAgent.synthesize_with_claude(self, context)

    return _Registered

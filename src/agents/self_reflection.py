"""Agent 22: Self-Reflection Agent.

Runs weekly Sunday 3AM UTC. Gathers agent logs (7 days), error logs, business
metrics, and content performance. Sends ALL data to Claude Opus for synthesis,
categorizes findings into 8 categories, saves to improvements table, and sends
report to Slack.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

CATEGORIES = [
    "recurring_error",
    "missed_opportunity",
    "inefficiency",
    "blind_spot",
    "cross_learning",
    "drift",
    "quality",
    "new_idea",
]

ANALYSIS_SYSTEM_PROMPT = (
    "Tu es l'agent Self-Reflection de la Factory. Tu reçois tous les logs des agents "
    "des 7 derniers jours, les erreurs, les métriques business et la performance du contenu.\n"
    "Analyse tout et identifie des améliorations. Pour chaque finding:\n"
    "- Catégorise dans exactement une de: recurring_error, missed_opportunity, inefficiency, "
    "blind_spot, cross_learning, drift, quality, new_idea\n"
    "- Donne une description claire\n"
    "- Propose une action concrète\n"
    "- Score d'impact 1-10 (10 = critique)\n"
    "Réponds en JSON: {\"findings\": [{\"category\": \"...\", \"description\": \"...\", "
    "\"proposed_action\": \"...\", \"impact_score\": N, \"target_agent\": \"...\"}]}"
)


async def _send_slack_report(report_md: str) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                settings.SLACK_WEBHOOK_URL,
                json={"text": report_md[:3800]},
            )
    except Exception:
        logger.warning("self_reflection_slack_failed")


class SelfReflectionAgent(BaseAgent):
    """Weekly self-reflection — Sunday 3AM UTC."""

    agent_name = "self_reflection"
    default_model = "opus"

    async def gather_data(self, context) -> dict:
        """Read agent_logs (7 days), error logs, business metrics, content performance."""
        async with SessionLocal() as db:
            agent_logs = (
                await db.execute(
                    text(
                        "SELECT agent_name, action, result, status, cost_usd, "
                        "duration_seconds, error_message, created_at "
                        "FROM agent_logs WHERE created_at > NOW() - INTERVAL '7 days' "
                        "ORDER BY created_at DESC"
                    )
                )
            ).fetchall()

            error_logs = (
                await db.execute(
                    text(
                        "SELECT agent_name, action, error_message, created_at "
                        "FROM agent_logs WHERE status = 'error' AND created_at > NOW() - INTERVAL '7 days' "
                        "ORDER BY created_at DESC"
                    )
                )
            ).fetchall()

            business_metrics = (
                await db.execute(
                    text(
                        "SELECT b.id, b.name, b.status, b.kill_score, b.mrr, b.customers_count, "
                        "ds.mrr AS snapshot_mrr, ds.customers_active, ds.api_cost_usd "
                        "FROM businesses b "
                        "LEFT JOIN LATERAL ("
                        "  SELECT business_id, mrr, customers_active, api_cost_usd "
                        "  FROM daily_snapshots WHERE business_id = b.id "
                        "  ORDER BY date DESC LIMIT 1"
                        ") ds ON ds.business_id = b.id "
                        "WHERE b.status IN ('live','pre_launch','building')"
                    )
                )
            ).fetchall()

            content_perf = (
                await db.execute(
                    text(
                        "SELECT business_id, type, status, "
                        "COALESCE((metrics->>'views')::int, 0) AS views, "
                        "COALESCE((metrics->>'clicks')::int, 0) AS clicks, created_at "
                        "FROM content WHERE created_at > NOW() - INTERVAL '7 days' "
                        "ORDER BY created_at DESC LIMIT 200"
                    )
                )
            ).fetchall()

        agent_logs_data = [
            {
                "agent_name": r.agent_name,
                "action": r.action,
                "status": r.status,
                "cost_usd": float(r.cost_usd) if r.cost_usd else None,
                "duration_seconds": float(r.duration_seconds) if r.duration_seconds else None,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in agent_logs
        ]
        error_logs_data = [
            {
                "agent_name": r.agent_name,
                "action": r.action,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in error_logs
        ]
        business_data = [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "kill_score": float(r.kill_score) if r.kill_score else None,
                "mrr": float(r.mrr) if r.mrr else None,
                "customers_count": r.customers_count,
            }
            for r in business_metrics
        ]
        content_data = [
            {
                "business_id": r.business_id,
                "type": r.type,
                "status": r.status,
                "views": r.views or 0,
                "clicks": r.clicks or 0,
            }
            for r in content_perf
        ]

        return {
            "agent_logs": agent_logs_data[:500],
            "error_logs": error_logs_data,
            "business_metrics": business_data,
            "content_performance": content_data,
        }

    async def analyze(self, context) -> dict:
        """Send ALL data to Claude Opus for synthesis."""
        data = context.step_output("gather_data")
        payload = json.dumps(data, default=str)

        model_tier = await self.check_budget()
        response, cost = await call_claude(
            model_tier=model_tier,
            system=ANALYSIS_SYSTEM_PROMPT,
            user=payload,
            max_tokens=4096,
            temperature=0.2,
        )

        await self.log_execution(
            action="analyze",
            result={"findings_count": 0},
            cost_usd=cost,
        )

        return {"raw_response": response, "cost_usd": cost}

    async def categorize_findings(self, context) -> dict:
        """Parse Claude response into structured findings (8 categories)."""
        data = context.step_output("analyze")
        raw = data.get("raw_response", "")

        findings = []
        try:
            if "{" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                parsed = json.loads(raw[start:end])
                for f in parsed.get("findings", []):
                    cat = f.get("category", "").strip().lower().replace(" ", "_")
                    if cat not in CATEGORIES:
                        cat = "quality"
                    findings.append({
                        "category": cat,
                        "description": str(f.get("description", ""))[:2000],
                        "proposed_action": str(f.get("proposed_action", ""))[:2000],
                        "impact_score": min(10, max(1, float(f.get("impact_score", 5)))),
                        "target_agent": str(f.get("target_agent", "")) or None,
                    })
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("self_reflection_parse_failed", error=str(e))

        return {"findings": findings}

    async def save_improvements(self, context) -> dict:
        """Insert findings to improvements table."""
        data = context.step_output("categorize_findings")
        findings = data.get("findings", [])

        if not findings:
            return {"saved": 0}

        async with SessionLocal() as db:
            for f in findings:
                await db.execute(
                    text(
                        "INSERT INTO improvements "
                        "(proposed_by, target_agent, category, description, proposed_action, impact_score) "
                        "VALUES (:by, :target, :cat, :desc, :action, :impact)"
                    ),
                    {
                        "by": self.agent_name,
                        "target": f.get("target_agent"),
                        "cat": f["category"],
                        "desc": f["description"],
                        "action": f["proposed_action"],
                        "impact": f["impact_score"],
                    },
                )
            await db.commit()

        return {"saved": len(findings)}

    async def send_report(self, context) -> dict:
        """Send summary report to Slack."""
        data = context.step_output("categorize_findings")
        findings = data.get("findings", [])

        report = (
            f":brain: *Self-Reflection Weekly Report* — "
            f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}\n\n"
            f"Found {len(findings)} improvement(s).\n\n"
        )
        for i, f in enumerate(findings[:10], 1):
            report += f"{i}. [{f['category']}] {f['description'][:150]}... (impact: {f['impact_score']})\n"

        await _send_slack_report(report)
        return {"report_sent": True, "findings_count": len(findings)}


def register(hatchet_instance) -> type:
    """Register SelfReflectionAgent as a Hatchet workflow."""
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="self-reflection", on_crons=["0 8 * * 0"])
    class _RegisteredSelfReflectionAgent(SelfReflectionAgent):
        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def gather_data(self, context: Context) -> dict:
            return await SelfReflectionAgent.gather_data(self, context)

        @hatchet_instance.task(execution_timeout="15m", retries=2)
        async def analyze(self, context: Context) -> dict:
            return await SelfReflectionAgent.analyze(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def categorize_findings(self, context: Context) -> dict:
            return await SelfReflectionAgent.categorize_findings(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=2)
        async def save_improvements(self, context: Context) -> dict:
            return await SelfReflectionAgent.save_improvements(self, context)

        @hatchet_instance.task(execution_timeout="1m", retries=1)
        async def send_report(self, context: Context) -> dict:
            return await SelfReflectionAgent.send_report(self, context)

    return _RegisteredSelfReflectionAgent

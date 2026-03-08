"""Agent 1: Meta Orchestrator — the CEO agent.

Runs daily at 6 AM ET. Gathers metrics from all businesses, asks Claude Opus
to prioritize and decide which agents to trigger, then executes those decisions
and sends a Slack digest.

Handles day-0 (zero businesses) by kicking off idea discovery.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "meta_orchestrator.txt"
ET = timezone(timedelta(hours=-5))


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


async def _gather_business_summaries(db) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT id, name, slug, status, mrr, customers_count, kill_score, "
                "launched_at, created_at FROM businesses ORDER BY id"
            )
        )
    ).fetchall()
    return [
        {
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "status": r.status,
            "mrr": float(r.mrr) if r.mrr else 0,
            "customers": r.customers_count or 0,
            "kill_score": float(r.kill_score) if r.kill_score else None,
            "launched_at": r.launched_at.isoformat() if r.launched_at else None,
            "age_days": (datetime.now(tz=timezone.utc) - r.created_at).days if r.created_at else 0,
        }
        for r in rows
    ]


async def _gather_snapshots(db, business_ids: list[int]) -> dict:
    """Latest daily snapshots for each business (7-day and 30-day windows)."""
    if not business_ids:
        return {}
    rows = (
        await db.execute(
            text(
                "SELECT business_id, date, mrr, customers_active, customers_new, "
                "customers_churned, leads_new, leads_converted, api_cost_usd, kill_score "
                "FROM daily_snapshots "
                "WHERE business_id = ANY(:ids) AND date > CURRENT_DATE - 30 "
                "ORDER BY business_id, date DESC"
            ),
            {"ids": business_ids},
        )
    ).fetchall()
    grouped: dict[int, list] = {}
    for r in rows:
        grouped.setdefault(r.business_id, []).append(
            {
                "date": r.date.isoformat(),
                "mrr": float(r.mrr) if r.mrr else 0,
                "active": r.customers_active or 0,
                "new": r.customers_new or 0,
                "churned": r.customers_churned or 0,
                "leads_new": r.leads_new or 0,
                "leads_converted": r.leads_converted or 0,
                "api_cost": float(r.api_cost_usd) if r.api_cost_usd else 0,
                "kill_score": float(r.kill_score) if r.kill_score else None,
            }
        )
    return grouped


async def _gather_errors_24h(db) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT agent_name, action, error_message, created_at "
                "FROM agent_logs "
                "WHERE status = 'error' AND created_at > NOW() - INTERVAL '24 hours' "
                "ORDER BY created_at DESC LIMIT 50"
            )
        )
    ).fetchall()
    return [
        {
            "agent": r.agent_name,
            "action": r.action,
            "error": r.error_message,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def _gather_error_rates_24h(db) -> list[dict]:
    """Per-agent error rates for the last 24 hours."""
    rows = (
        await db.execute(
            text(
                "SELECT agent_name, "
                "COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE status = 'error') AS errors "
                "FROM agent_logs "
                "WHERE created_at > NOW() - INTERVAL '24 hours' "
                "GROUP BY agent_name"
            )
        )
    ).fetchall()
    return [
        {
            "agent": r.agent_name,
            "total": r.total,
            "errors": r.errors,
            "error_rate": round(r.errors / r.total, 3) if r.total else 0,
        }
        for r in rows
    ]


async def _gather_improvements(db) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT target_agent, category, description, impact_score "
                "FROM improvements "
                "WHERE status = 'proposed' "
                "ORDER BY impact_score DESC NULLS LAST LIMIT 10"
            )
        )
    ).fetchall()
    return [
        {
            "agent": r.target_agent,
            "category": r.category,
            "description": r.description,
            "impact": float(r.impact_score) if r.impact_score else None,
        }
        for r in rows
    ]


async def _gather_budget_yesterday(db) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT agent_name, SUM(cost_usd) AS total "
                "FROM budget_tracking "
                "WHERE date = CURRENT_DATE - 1 "
                "GROUP BY agent_name ORDER BY total DESC"
            )
        )
    ).fetchall()
    by_agent = {r.agent_name: float(r.total) for r in rows}
    return {
        "total_usd": sum(by_agent.values()),
        "limit_usd": settings.DAILY_BUDGET_LIMIT_USD,
        "by_agent": by_agent,
    }


async def _gather_lead_pipeline(db, business_ids: list[int]) -> dict:
    if not business_ids:
        return {}
    rows = (
        await db.execute(
            text(
                "SELECT business_id, status, COUNT(*) AS cnt "
                "FROM leads "
                "WHERE business_id = ANY(:ids) "
                "GROUP BY business_id, status"
            ),
            {"ids": business_ids},
        )
    ).fetchall()
    pipeline: dict[int, dict] = {}
    for r in rows:
        pipeline.setdefault(r.business_id, {})[r.status] = r.cnt
    return pipeline


async def _send_slack_digest(decisions: dict, businesses: list[dict]) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        logger.info("slack_skip", reason="no webhook configured")
        return

    biz_count = len(businesses)
    total_mrr = sum(b["mrr"] for b in businesses)
    priorities = decisions.get("priorities", [])
    alerts = decisions.get("alerts", [])
    human = decisions.get("human_needed", [])
    triggers = decisions.get("agent_triggers", [])

    lines = [
        f":factory: *Factory Daily Digest* — {datetime.now(tz=ET).strftime('%A %B %d, %Y')}",
        f"Businesses: *{biz_count}* | Total MRR: *${total_mrr:,.2f}*",
        "",
        "*Top priorities:*",
    ]
    for i, p in enumerate(priorities[:3], 1):
        lines.append(f"  {i}. {p}")

    if triggers:
        lines.append(f"\n*Agent triggers:* {len(triggers)} workflows queued")
    if alerts:
        lines.append("\n:rotating_light: *Alerts:*")
        for a in alerts:
            lines.append(f"  • {a}")
    if human:
        lines.append("\n:raising_hand: *Human needed:*")
        for h in human:
            lines.append(f"  • {h}")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json={"text": "\n".join(lines)})
    except Exception:
        logger.warning("slack_digest_failed")


class MetaOrchestrator(BaseAgent):
    """CEO agent — daily 6 AM ET (11 UTC) coordination loop."""

    agent_name = "meta_orchestrator"
    default_model = "opus"

    async def gather_all_metrics(self, context) -> dict:
        """Read all operational data for the Opus decision prompt."""
        async with SessionLocal() as db:
            businesses = await _gather_business_summaries(db)
            biz_ids = [b["id"] for b in businesses]
            snapshots = await _gather_snapshots(db, biz_ids)
            errors = await _gather_errors_24h(db)
            error_rates = await _gather_error_rates_24h(db)
            improvements = await _gather_improvements(db)
            budget = await _gather_budget_yesterday(db)
            pipeline = await _gather_lead_pipeline(db, biz_ids)

        return {
            "businesses": businesses,
            "snapshots": snapshots,
            "errors_24h": errors,
            "error_rates_24h": error_rates,
            "pending_improvements": improvements,
            "budget_yesterday": budget,
            "lead_pipeline": pipeline,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    async def analyze_and_decide(self, context) -> dict:
        """Send all metrics to Claude Opus and get back structured decisions."""
        metrics = context.step_output("gather_all_metrics")
        model_tier = await self.check_budget()

        system_prompt = _load_prompt()
        user_payload = json.dumps(metrics, default=str)

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=user_payload,
            max_tokens=4096,
            temperature=0.2,
        )

        await self.log_execution(
            action="analyze_and_decide",
            result={"raw_length": len(response_text)},
            cost_usd=cost,
        )

        try:
            decisions = json.loads(response_text)
        except json.JSONDecodeError:
            logger.error("meta_orchestrator_bad_json", raw=response_text[:500])
            decisions = {
                "priorities": ["Fix meta orchestrator JSON output"],
                "agent_triggers": [],
                "budget_allocation": {},
                "alerts": ["Meta Orchestrator returned non-JSON — check prompt"],
                "human_needed": [],
                "reasoning": "JSON parse failed, returning safe defaults",
            }

        return {"decisions": decisions, "cost_usd": cost}

    async def execute_decisions(self, context, *, _hatchet_admin=None) -> dict:
        """Trigger agents, send Slack digest, log everything.

        _hatchet_admin is injectable for tests; in production the registered
        workflow passes the real hatchet admin client.
        """
        analysis = context.step_output("analyze_and_decide")
        metrics = context.step_output("gather_all_metrics")
        decisions = analysis["decisions"]

        admin = _hatchet_admin

        triggered = []
        for trigger in decisions.get("agent_triggers", []):
            workflow_name = trigger.get("agent")
            workflow_input = trigger.get("input", {})
            if not workflow_name:
                continue
            if admin is None:
                logger.warning("no_hatchet_admin", workflow=workflow_name)
                continue
            try:
                await admin.run_workflow(workflow_name, workflow_input)
                triggered.append(workflow_name)
                logger.info("agent_triggered", workflow=workflow_name, reason=trigger.get("reason"))
            except Exception as exc:
                logger.error("agent_trigger_failed", workflow=workflow_name, error=str(exc))

        await _send_slack_digest(decisions, metrics.get("businesses", []))

        await self.log_execution(
            action="execute_decisions",
            result={
                "triggered": triggered,
                "priorities": decisions.get("priorities", []),
                "alerts_count": len(decisions.get("alerts", [])),
            },
        )

        return {
            "triggered_agents": triggered,
            "decisions": decisions,
        }


def register(hatchet_instance) -> type:
    """Register the MetaOrchestrator as a Hatchet workflow.

    Called from main.py at startup — keeps this module importable without
    a live Hatchet token (critical for tests).
    """

    @hatchet_instance.workflow(name="meta-orchestrator", on_crons=["0 11 * * *"])
    class _RegisteredMetaOrchestrator(MetaOrchestrator):
        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def gather_all_metrics(self, context) -> dict:
            return await MetaOrchestrator.gather_all_metrics(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def analyze_and_decide(self, context) -> dict:
            return await MetaOrchestrator.analyze_and_decide(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def execute_decisions(self, context) -> dict:
            return await MetaOrchestrator.execute_decisions(
                self, context, _hatchet_admin=hatchet_instance.client.admin
            )

    return _RegisteredMetaOrchestrator

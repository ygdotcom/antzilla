"""Agent 15: Competitor Watch.

Cron weekly Wednesday 4AM UTC. Scrapes competitor sites from GTM playbook,
detects changes via content hashing, checks pricing, Product Hunt, analyzes
with Claude, alerts on critical changes (price drops, new features, funding).
"""

from __future__ import annotations

import hashlib
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


class CompetitorWatchAgent(BaseAgent):
    """Weekly competitor monitoring with change detection and critical alerts."""

    agent_name = "competitor_watch"
    default_model = "sonnet"

    async def scrape_competitors(self, context) -> dict:
        """For each business, scrape competitor URLs from GTM playbook, detect changes via content hashing."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"businesses": 0, "changes_detected": 0}

        all_changes = []
        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            competitor_urls = playbook.get("competitor_urls", [])
            if isinstance(competitor_urls, dict):
                competitor_urls = [{"name": k, "url": v} for k, v in competitor_urls.items()]
            elif isinstance(competitor_urls, list) and competitor_urls and isinstance(competitor_urls[0], str):
                competitor_urls = [{"name": c, "url": f"https://{c.lower().replace(' ', '')}.com"} for c in competitor_urls]

            if not competitor_urls:
                continue

            current_hashes = {}
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                for comp in competitor_urls:
                    url = comp.get("url") if isinstance(comp, dict) else comp
                    name = comp.get("name", url) if isinstance(comp, dict) else url
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        content = resp.text[:50000]
                        h = hashlib.sha256(content.encode()).hexdigest()
                        current_hashes[name] = {"hash": h, "url": url}
                    except Exception as exc:
                        logger.warning("competitor_scrape_failed", url=url, error=str(exc))

            prev_hashes = {}
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        text(
                            "SELECT result FROM agent_logs "
                            "WHERE agent_name = 'competitor_watch' AND action = 'log_report' "
                            "AND status = 'success' ORDER BY created_at DESC LIMIT 1"
                        ),
                    )
                ).fetchone()

            if row and row.result:
                try:
                    data = row.result if isinstance(row.result, dict) else json.loads(str(row.result))
                    details = data.get("scrape", {}).get("details", [])
                    for d in details:
                        if d.get("business_id") == biz["id"]:
                            prev_hashes = d.get("hashes", {})
                            break
                except Exception:
                    pass

            changes = []
            for name, info in current_hashes.items():
                prev = prev_hashes.get(name, {})
                if prev and prev.get("hash") != info["hash"]:
                    changes.append({"competitor": name, "url": info["url"], "change": "content_updated"})

            all_changes.extend(
                [{"business_id": biz["id"], "business_slug": biz["slug"], "changes": changes, "hashes": current_hashes}]
            )

        return {"businesses": len(businesses), "changes_detected": sum(len(c["changes"]) for c in all_changes), "details": all_changes}

    async def check_pricing_changes(self, context) -> dict:
        """Look for price changes in scraped content."""
        scrape_out = context.step_output("scrape_competitors")
        details = scrape_out.get("details", [])
        pricing_changes = []
        for d in details:
            for ch in d.get("changes", []):
                if "price" in ch.get("competitor", "").lower() or "pricing" in ch.get("url", "").lower():
                    pricing_changes.append({**ch, "business_id": d["business_id"]})
        return {"pricing_changes": pricing_changes}

    async def check_product_hunt(self, context) -> dict:
        """Search for new launches in category (placeholder — would use Product Hunt API)."""
        businesses = await get_active_businesses()
        launches = []
        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue
            niche = playbook.get("icp", {}).get("niche", "") or playbook.get("product", {}).get("name", "")
            if niche and getattr(settings, "PRODUCT_HUNT_TOKEN", None):
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            "https://api.producthunt.com/v2/api/graphql",
                            headers={"Authorization": f"Bearer {settings.PRODUCT_HUNT_TOKEN}"},
                            json={"query": "query { posts(first: 5) { edges { node { name url tagline } } } }"},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            posts = data.get("data", {}).get("posts", {}).get("edges", [])
                            launches.extend([{"business_id": biz["id"], "launch": p["node"]} for p in posts])
                except Exception as exc:
                    logger.debug("product_hunt_check_skipped", business_id=biz["id"], error=str(exc))
        return {"new_launches": launches}

    async def analyze_with_claude(self, context) -> dict:
        """Send changes to Claude for analysis."""
        scrape_out = context.step_output("scrape_competitors")
        pricing_out = context.step_output("check_pricing_changes")
        ph_out = context.step_output("check_product_hunt")

        summary = {
            "changes": scrape_out.get("details", []),
            "pricing_changes": pricing_out.get("pricing_changes", []),
            "product_hunt_launches": ph_out.get("new_launches", []),
        }
        has_changes = any(len(d.get("changes", [])) > 0 for d in (summary.get("changes") or []))
        has_pricing = len(summary.get("pricing_changes") or []) > 0
        has_launches = len(summary.get("product_hunt_launches") or []) > 0
        if not (has_changes or has_pricing or has_launches):
            return {"analysis": None, "critical": False}

        model = await self.check_budget()
        response, cost = await call_claude(
            model_tier=model,
            system="Tu es un analyste concurrentiel. Analyse les changements détectés (sites concurrents, prix, lancements Product Hunt) et identifie ce qui est CRITIQUE: baisses de prix, nouvelles fonctionnalités majeures, financement. Réponds en JSON: {\"critical\": bool, \"summary\": str, \"recommendations\": [str]}",
            user=json.dumps(summary, indent=2),
        )
        try:
            analysis = json.loads(response)
        except json.JSONDecodeError:
            analysis = {"critical": False, "summary": response[:500], "recommendations": []}

        await self.log_execution(action="analyze_with_claude", result=analysis, cost_usd=cost)
        return {"analysis": analysis, "cost_usd": cost}

    async def alert_if_critical(self, context) -> dict:
        """Slack alert on price drops, new features, funding."""
        analysis_out = context.step_output("analyze_with_claude")
        analysis = analysis_out.get("analysis")
        if not analysis or not analysis.get("critical"):
            return {"alerted": False}

        if not settings.SLACK_WEBHOOK_URL:
            logger.warning("slack_webhook_missing", agent=self.agent_name)
            return {"alerted": False}

        text_body = (
            f":warning: *Competitor Watch — Critical Alert*\n"
            f"{analysis.get('summary', 'Critical change detected')}\n"
            f"Recommendations: {', '.join(analysis.get('recommendations', [])[:3])}"
        )
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(settings.SLACK_WEBHOOK_URL, json={"text": text_body})
            return {"alerted": True}
        except Exception as exc:
            logger.warning("slack_alert_failed", error=str(exc))
            return {"alerted": False}

    async def log_report(self, context) -> dict:
        """Save full report to agent_logs."""
        scrape_out = context.step_output("scrape_competitors")
        analysis_out = context.step_output("analyze_with_claude")
        alert_out = context.step_output("alert_if_critical")

        report = {
            "scrape": scrape_out,
            "analysis": analysis_out.get("analysis"),
            "alerted": alert_out.get("alerted", False),
        }
        await self.log_execution(action="log_report", result=report)
        return {"logged": True}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="competitor-watch", on_crons=["0 9 * * 3"], timeout="20m")
    class _Registered(CompetitorWatchAgent):
        @hatchet_instance.step(timeout="10m", retries=1)
        async def scrape_competitors(self, context: Context) -> dict:
            return await CompetitorWatchAgent.scrape_competitors(self, context)

        @hatchet_instance.step(timeout="5m", retries=1, parents=["scrape_competitors"])
        async def check_pricing_changes(self, context: Context) -> dict:
            return await CompetitorWatchAgent.check_pricing_changes(self, context)

        @hatchet_instance.step(timeout="5m", retries=1, parents=["scrape_competitors"])
        async def check_product_hunt(self, context: Context) -> dict:
            return await CompetitorWatchAgent.check_product_hunt(self, context)

        @hatchet_instance.step(timeout="5m", retries=1, parents=["check_pricing_changes", "check_product_hunt"])
        async def analyze_with_claude(self, context: Context) -> dict:
            return await CompetitorWatchAgent.analyze_with_claude(self, context)

        @hatchet_instance.step(timeout="2m", retries=1, parents=["analyze_with_claude"])
        async def alert_if_critical(self, context: Context) -> dict:
            return await CompetitorWatchAgent.alert_if_critical(self, context)

        @hatchet_instance.step(timeout="2m", retries=1, parents=["alert_if_critical"])
        async def log_report(self, context: Context) -> dict:
            return await CompetitorWatchAgent.log_report(self, context)

    return _Registered

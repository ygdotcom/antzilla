"""Sub-agent 12c: Signal Monitor.

Cron every 4 hours.  Monitors buying signals defined in each business's
GTM Playbook (gtm_playbooks.signals).  When a signal fires, bumps the
lead's score, records it in the signals table, and fast-tracks hot leads
into the outreach queue.

Signal types: new_business_registration, building_permit_issued,
competitor_complaint, job_posting (hiring_estimator), website_visitor,
regulation_change.
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

logger = structlog.get_logger()


async def _check_new_registrations(signal_cfg: dict, business_id: int) -> list[dict]:
    """Poll REQ for new business registrations matching NAICS codes."""
    source = signal_cfg.get("source", "req_registry")
    naics = signal_cfg.get("naics", "")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://www.registreentreprises.gouv.qc.ca/RQAnonymousWebAPI/api/recherche",
                params={"motsCles": naics, "derniers30jours": "true"},
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                entries = resp.json()
                if isinstance(entries, dict):
                    entries = entries.get("resultats", [])
                return [
                    {
                        "signal_type": "new_business_registration",
                        "source": source,
                        "data": {"name": e.get("nom", ""), "neq": e.get("neq", "")},
                        "match_name": e.get("nom", ""),
                    }
                    for e in entries[:20]
                ]
            return []
        except Exception as exc:
            logger.warning("signal_req_failed", error=str(exc))
            return []


async def _check_building_permits(signal_cfg: dict, business_id: int) -> list[dict]:
    """Scrape municipal open data for new building permits."""
    source = signal_cfg.get("source", "municipal_data")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://donnees.montreal.ca/api/3/action/datastore_search",
                params={"resource_id": "permis-construction", "limit": 20},
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("result", {}).get("records", [])
                return [
                    {
                        "signal_type": "building_permit_issued",
                        "source": source,
                        "data": {"permit_id": r.get("NO_PERMIS"), "address": r.get("ADRESSE")},
                        "match_name": r.get("NOM_PROPRIETAIRE", ""),
                    }
                    for r in records
                ]
            return []
        except Exception as exc:
            logger.warning("signal_permits_failed", error=str(exc))
            return []


async def _check_competitor_complaints(signal_cfg: dict, business_id: int) -> list[dict]:
    """Monitor Google Reviews for competitor complaints (placeholder)."""
    return []


async def _check_job_postings(signal_cfg: dict, business_id: int) -> list[dict]:
    """Scrape Indeed.ca for job postings the product replaces."""
    keywords = signal_cfg.get("keywords", signal_cfg.get("query", ""))
    if not keywords:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://www.google.ca/search",
                params={"q": f"site:indeed.ca {keywords} Quebec", "num": 10},
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            # Parse search results for job listings
            return []  # production: parse and extract
        except Exception:
            return []


async def _check_website_visitors(signal_cfg: dict, business_id: int) -> list[dict]:
    """Check Plausible API for website visitors matching leads."""
    if not settings.PLAUSIBLE_BASE_URL:
        return []
    # In production: query Plausible API for visitor companies via reverse IP
    return []


SIGNAL_HANDLERS = {
    "new_business_registration": _check_new_registrations,
    "building_permit_issued": _check_building_permits,
    "competitor_complaint": _check_competitor_complaints,
    "hiring_estimator": _check_job_postings,
    "job_posting": _check_job_postings,
    "website_visit": _check_website_visitors,
}


class SignalMonitor(BaseAgent):
    """Monitors buying signals and fast-tracks hot leads."""

    agent_name = "signal_monitor"
    default_model = "haiku"

    async def scan_signals(self, context) -> dict:
        """Scan all configured signal sources for each active business."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"businesses_scanned": 0, "signals_detected": 0}

        total_signals = 0
        results = []

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            signal_configs = playbook.get("signals", [])
            biz_signals = 0

            for sig_cfg in signal_configs:
                sig_type = sig_cfg.get("type", "")
                handler = SIGNAL_HANDLERS.get(sig_type)
                if not handler:
                    continue

                detected = await handler(sig_cfg, biz["id"])
                weight = sig_cfg.get("weight", 5)

                async with SessionLocal() as db:
                    for signal in detected:
                        # Try to match signal to existing lead
                        match_name = signal.get("match_name", "")
                        lead_id = None
                        if match_name:
                            lead_row = (
                                await db.execute(
                                    text(
                                        "SELECT id FROM leads WHERE business_id = :biz "
                                        "AND name ILIKE :pattern LIMIT 1"
                                    ),
                                    {"biz": biz["id"], "pattern": f"%{match_name[:30]}%"},
                                )
                            ).fetchone()
                            lead_id = lead_row.id if lead_row else None

                        # Insert signal
                        await db.execute(
                            text(
                                "INSERT INTO signals (business_id, lead_id, signal_type, "
                                "source, data, weight) "
                                "VALUES (:biz, :lead, :type, :source, :data, :weight)"
                            ),
                            {
                                "biz": biz["id"],
                                "lead": lead_id,
                                "type": signal["signal_type"],
                                "source": signal.get("source"),
                                "data": json.dumps(signal.get("data", {})),
                                "weight": weight,
                            },
                        )

                        # Bump lead score if matched
                        if lead_id:
                            await db.execute(
                                text(
                                    "UPDATE leads SET signal_type = :type, "
                                    "signal_date = NOW(), "
                                    "signal_data = :data, "
                                    "score = LEAST(100, score + :weight) "
                                    "WHERE id = :id"
                                ),
                                {
                                    "type": signal["signal_type"],
                                    "data": json.dumps(signal.get("data", {})),
                                    "weight": weight,
                                    "id": lead_id,
                                },
                            )

                        biz_signals += 1

                    await db.commit()

            total_signals += biz_signals
            results.append({"business_id": biz["id"], "signals": biz_signals})

            if biz_signals > 0:
                await self.log_execution(
                    action="scan_signals",
                    result={"signals_detected": biz_signals},
                    business_id=biz["id"],
                )

        return {"businesses_scanned": len(results), "signals_detected": total_signals, "details": results}


def register(hatchet_instance) -> type:

    @hatchet_instance.workflow(name="signal-monitor", on_crons=["0 */4 * * *"])
    class _Registered(SignalMonitor):
        @hatchet_instance.task(execution_timeout="12m", retries=1)
        async def scan_signals(self, context) -> dict:
            return await SignalMonitor.scan_signals(self, context)

    return _Registered

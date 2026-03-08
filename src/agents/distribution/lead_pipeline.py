"""Sub-agent 12a: Lead Pipeline.

Daily cron per active business. Reads `gtm_playbooks` config and generates
leads via Serper Places API (Google Maps), derived from the ICP description.

Deduplicates against existing leads via fuzzy name matching before insert.
"""

from __future__ import annotations

import json
import re
import urllib.parse

import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses, load_playbook
from src.db import SessionLocal
from src.integrations import serper

logger = structlog.get_logger()


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def _build_search_queries(playbook: dict) -> list[dict]:
    """Derive Serper Places search queries from the GTM playbook.

    Returns a list of {"q": ..., "location": ...} dicts.
    """
    queries: list[dict] = []

    lead_sources = playbook.get("lead_sources", [])
    lead_sources.sort(key=lambda s: s.get("priority", 99))
    for src in lead_sources:
        q = src.get("query", "")
        if q:
            queries.append({
                "q": q,
                "location": src.get("geo", src.get("location", "Canada")),
                "num": src.get("num", 20),
            })

    if not queries:
        icp = playbook.get("icp", {})
        icp_desc = icp.get("description", "") if isinstance(icp, dict) else str(icp)
        industry = playbook.get("industry", "")
        vertical = playbook.get("vertical", "")
        search_term = icp_desc or industry or vertical
        if search_term:
            queries.append({
                "q": search_term,
                "location": playbook.get("geo", "Canada"),
                "num": 20,
            })

    return queries


async def _search_serper_places(queries: list[dict]) -> list[dict]:
    """Call Serper Places API for each query and return parsed leads."""
    all_leads: list[dict] = []
    seen_names: set[str] = set()

    for qcfg in queries:
        q = qcfg["q"]
        location = qcfg.get("location", "Canada")
        num = qcfg.get("num", 20)

        results = await serper.search_maps(q, location, num=num)

        for r in results:
            name = r.get("name", "").strip()
            if not name:
                continue
            norm = _normalize(name)
            if norm in seen_names:
                continue
            seen_names.add(norm)

            address = r.get("address", "")
            province = _extract_province(address)

            all_leads.append({
                "name": name,
                "company": name,
                "phone": r.get("phone", "") or None,
                "address": address or None,
                "source": "google_maps",
                "source_url": f"https://maps.google.com/?q={urllib.parse.quote_plus(name + ' ' + address)}",
                "consent_type": "conspicuous_publication",
                "province": province,
                "enrichment_data": json.dumps({
                    "address": address,
                    "rating": r.get("rating"),
                    "reviews": r.get("reviews"),
                    "website": r.get("website"),
                    "place_id": r.get("place_id"),
                    "search_query": q,
                }),
            })

    return all_leads


_CA_PROVINCES = {
    "AB": "AB", "BC": "BC", "MB": "MB", "NB": "NB",
    "NL": "NL", "NS": "NS", "NT": "NT", "NU": "NU",
    "ON": "ON", "PE": "PE", "QC": "QC", "SK": "SK", "YT": "YT",
    "ALBERTA": "AB", "BRITISH COLUMBIA": "BC", "MANITOBA": "MB",
    "NEW BRUNSWICK": "NB", "NEWFOUNDLAND": "NL", "NOVA SCOTIA": "NS",
    "ONTARIO": "ON", "QUEBEC": "QC", "QUÉBEC": "QC",
    "SASKATCHEWAN": "SK", "PRINCE EDWARD ISLAND": "PE",
}


def _extract_province(address: str) -> str | None:
    """Best-effort province extraction from a Google Maps address string."""
    if not address:
        return None
    upper = address.upper()
    for token, code in _CA_PROVINCES.items():
        if token in upper:
            return code
    return None


class LeadPipeline(BaseAgent):
    """Serper Places-based lead generation, driven by GTM Playbook config."""

    agent_name = "lead_pipeline"
    default_model = "haiku"

    async def generate_leads(self, context) -> dict:
        """Fetch leads from Serper Places for all active businesses."""
        businesses = await get_active_businesses()
        if not businesses:
            logger.info("lead_pipeline_skip", reason="no active businesses")
            return {"businesses_processed": 0, "total_leads": 0}

        total = 0
        results = []

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                logger.warning("lead_pipeline_no_playbook", business_id=biz["id"])
                continue

            queries = _build_search_queries(playbook)
            if not queries:
                logger.warning("lead_pipeline_no_queries", business_id=biz["id"])
                continue

            raw_leads = await _search_serper_places(queries)

            inserted = 0
            skipped_dup = 0
            async with SessionLocal() as db:
                existing = await _load_existing_names(db, biz["id"])

                for lead in raw_leads:
                    name = lead.get("name", "")
                    if not name:
                        continue
                    norm = _normalize(name)
                    if any(norm in ex or ex in norm for ex in existing if len(ex) > 3):
                        skipped_dup += 1
                        continue

                    await db.execute(
                        text(
                            "INSERT INTO leads "
                            "(business_id, name, company, phone, source, source_url, "
                            "consent_type, province, enrichment_data, status) "
                            "VALUES (:biz, :name, :company, :phone, :source, :url, "
                            ":consent, :province, :enrich, 'new') "
                            "ON CONFLICT DO NOTHING"
                        ),
                        {
                            "biz": biz["id"],
                            "name": name,
                            "company": lead.get("company"),
                            "phone": lead.get("phone"),
                            "source": lead.get("source"),
                            "url": lead.get("source_url"),
                            "consent": lead.get("consent_type"),
                            "province": lead.get("province"),
                            "enrich": lead.get("enrichment_data"),
                        },
                    )
                    inserted += 1
                    existing.add(norm)

                await db.commit()

            total += inserted
            results.append({
                "business_id": biz["id"],
                "slug": biz["slug"],
                "leads_inserted": inserted,
                "duplicates_skipped": skipped_dup,
                "queries_run": len(queries),
            })
            logger.info(
                "lead_pipeline_done",
                business_id=biz["id"],
                slug=biz["slug"],
                raw=len(raw_leads),
                inserted=inserted,
                skipped=skipped_dup,
            )
            await self.log_execution(
                action="generate_leads",
                result={"queries": len(queries), "raw": len(raw_leads), "inserted": inserted},
                business_id=biz["id"],
            )

        return {"businesses_processed": len(results), "total_leads": total, "details": results}


async def _load_existing_names(db, business_id: int) -> set[str]:
    """Load normalized names of existing leads for dedup."""
    rows = (
        await db.execute(
            text("SELECT name FROM leads WHERE business_id = :biz"),
            {"biz": business_id},
        )
    ).fetchall()
    return {_normalize(r.name) for r in rows if r.name}


def register(hatchet_instance):
    agent = LeadPipeline()
    wf = hatchet_instance.workflow(name="lead-pipeline", on_crons=["0 11 * * *"])

    @wf.task(execution_timeout="25m", retries=1)
    async def generate_leads(input, ctx):
        return await agent.generate_leads(ctx)

    return wf

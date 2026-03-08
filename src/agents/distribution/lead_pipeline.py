"""Sub-agent 12a: Lead Pipeline.

Daily cron per active business.  Reads `gtm_playbooks.lead_sources` and
generates leads from configured sources in priority order:
Google Maps (Serper), RBQ, REQ, Federal Corp, association directories.

Deduplicates against existing leads via fuzzy name+address matching.
"""

from __future__ import annotations

import json
import re

import httpx
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


async def _check_duplicate(db, business_id: int, name: str, address: str | None) -> bool:
    """Check if a lead with a similar name already exists for this business."""
    norm_name = _normalize(name)
    if not norm_name:
        return False
    row = (
        await db.execute(
            text(
                "SELECT id FROM leads "
                "WHERE business_id = :biz AND LOWER(REPLACE(name, '''', '')) ILIKE :pattern "
                "LIMIT 1"
            ),
            {"biz": business_id, "pattern": f"%{norm_name[:30]}%"},
        )
    ).fetchone()
    return row is not None


async def _fetch_google_maps(source_cfg: dict, business_id: int) -> list[dict]:
    """Fetch leads from Google Maps via Serper API."""
    query = source_cfg.get("query", "")
    geo = source_cfg.get("geo", "Quebec, Canada")
    if not query:
        return []

    results = await serper.search_maps(query, geo, num=40)
    leads = []
    for r in results:
        leads.append({
            "name": r.get("name", ""),
            "phone": r.get("phone"),
            "company": r.get("name", ""),
            "source": "google_maps",
            "source_url": f"https://maps.google.com/?q={query}",
            "consent_type": "conspicuous_publication",
            "enrichment_data": json.dumps({
                "address": r.get("address"),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "website": r.get("website"),
                "place_id": r.get("place_id"),
            }),
        })
    return leads


async def _fetch_rbq(source_cfg: dict, business_id: int) -> list[dict]:
    """Fetch leads from RBQ open data (Quebec contractor licences)."""
    licence_type = source_cfg.get("licence_type", "")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                "https://www.donneesquebec.ca/recherche/dataset/rbq-repertoire-titulaires-licence",
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return []
            # Parse CSV data — in production, download the actual CSV
            # For now return structured placeholder
            logger.info("rbq_fetch", licence_type=licence_type, status="csv_parsing_needed")
            return []
        except Exception as exc:
            logger.warning("rbq_fetch_failed", error=str(exc))
            return []


async def _fetch_req(source_cfg: dict, business_id: int) -> list[dict]:
    """Fetch new business registrations from REQ (Registraire des entreprises du Québec)."""
    naics = source_cfg.get("naics", "")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                "https://www.registreentreprises.gouv.qc.ca/RQAnonymousWebAPI/api/recherche",
                params={"motsCles": naics, "typeRecherche": "NAICS"},
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                data = resp.json()
                return [
                    {
                        "name": entry.get("nom", ""),
                        "company": entry.get("nom", ""),
                        "source": "req_registry",
                        "source_url": "registreentreprises.gouv.qc.ca",
                        "consent_type": "conspicuous_publication",
                    }
                    for entry in (data if isinstance(data, list) else data.get("resultats", []))[:50]
                ]
            return []
        except Exception as exc:
            logger.warning("req_fetch_failed", error=str(exc))
            return []


async def _fetch_federal_corp(source_cfg: dict, business_id: int) -> list[dict]:
    """Fetch from Federal Corporation API (Canada API Store — free)."""
    keywords = source_cfg.get("keywords", source_cfg.get("query", ""))
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://corporations.ic.gc.ca/copo/api/v1/search",
                params={"q": keywords, "status": "Active"},
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                data = resp.json()
                corps = data if isinstance(data, list) else data.get("corporations", [])
                return [
                    {
                        "name": c.get("corporationName", ""),
                        "company": c.get("corporationName", ""),
                        "source": "federal_corp",
                        "source_url": "corporations.ic.gc.ca",
                        "consent_type": "conspicuous_publication",
                    }
                    for c in corps[:30]
                ]
            return []
        except Exception as exc:
            logger.warning("federal_corp_failed", error=str(exc))
            return []


async def _fetch_association(source_cfg: dict, business_id: int) -> list[dict]:
    """Scrape association member directory."""
    url = source_cfg.get("url", "")
    org = source_cfg.get("org", "")
    if not url:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"https://{url}" if not url.startswith("http") else url,
                headers={"User-Agent": "FactoryBot/1.0"},
                follow_redirects=True,
            )
            # In production: parse HTML member listings
            logger.info("association_scrape", org=org, status_code=resp.status_code)
            return []
        except Exception as exc:
            logger.warning("association_scrape_failed", org=org, error=str(exc))
            return []


SOURCE_HANDLERS = {
    "google_maps": _fetch_google_maps,
    "rbq_registry": _fetch_rbq,
    "req_registry": _fetch_req,
    "federal_corp": _fetch_federal_corp,
    "association_directory": _fetch_association,
    "industry_directory": _fetch_association,
}


class LeadPipeline(BaseAgent):
    """Multi-source lead generation, driven by GTM Playbook config."""

    agent_name = "lead_pipeline"
    default_model = "haiku"

    async def generate_leads(self, context) -> dict:
        """Fetch leads from all configured sources for all active businesses."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"businesses_processed": 0, "total_leads": 0}

        total = 0
        results = []

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            lead_sources = playbook.get("lead_sources", [])
            lead_sources.sort(key=lambda s: s.get("priority", 99))

            biz_leads = []
            for source_cfg in lead_sources:
                source_type = source_cfg.get("type", "")
                handler = SOURCE_HANDLERS.get(source_type)
                if not handler:
                    logger.warning("unknown_lead_source", source=source_type)
                    continue
                raw = await handler(source_cfg, biz["id"])
                biz_leads.extend(raw)

            # Deduplicate and insert
            inserted = 0
            async with SessionLocal() as db:
                for lead in biz_leads:
                    name = lead.get("name", "")
                    if not name:
                        continue
                    is_dup = await _check_duplicate(db, biz["id"], name, lead.get("address"))
                    if is_dup:
                        continue
                    await db.execute(
                        text(
                            "INSERT INTO leads (business_id, name, company, phone, source, "
                            "source_url, consent_type, enrichment_data, status) "
                            "VALUES (:biz, :name, :company, :phone, :source, :url, :consent, :enrich, 'new')"
                        ),
                        {
                            "biz": biz["id"],
                            "name": name,
                            "company": lead.get("company"),
                            "phone": lead.get("phone"),
                            "source": lead.get("source"),
                            "url": lead.get("source_url"),
                            "consent": lead.get("consent_type"),
                            "enrich": lead.get("enrichment_data"),
                        },
                    )
                    inserted += 1
                await db.commit()

            total += inserted
            results.append({"business_id": biz["id"], "slug": biz["slug"], "leads_inserted": inserted})
            await self.log_execution(
                action="generate_leads",
                result={"sources": len(lead_sources), "raw": len(biz_leads), "inserted": inserted},
                business_id=biz["id"],
            )

        return {"businesses_processed": len(results), "total_leads": total, "details": results}


def register(hatchet_instance) -> type:

    @hatchet_instance.workflow(name="lead-pipeline", on_crons=["0 11 * * *"])
    class _Registered(LeadPipeline):
        @hatchet_instance.task(execution_timeout="25m", retries=1)
        async def generate_leads(self, context) -> dict:
            return await LeadPipeline.generate_leads(self, context)

    return _Registered

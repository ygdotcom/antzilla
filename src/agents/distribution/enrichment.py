"""Sub-agent 12b: Enrichment Agent.

Waterfall enrichment: Apollo → Hunter → Dropcontact → website scrape.
ZeroBounce verification. Lead scoring 0-100.

Runs after Lead Pipeline completes or on-demand for new leads.
"""

from __future__ import annotations

import json
import re

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import load_playbook
from src.db import SessionLocal
from src.integrations import apollo, hunter, zerobounce

logger = structlog.get_logger()


def _extract_emails_from_html(html: str) -> list[str]:
    """Regex extraction of emails from web page content."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    found = re.findall(pattern, html)
    return list(set(found))[:5]


async def _scrape_website_contacts(domain: str) -> dict | None:
    """Scrape /contact, /about pages for emails and phones."""
    if not domain:
        return None
    base = f"https://{domain}" if not domain.startswith("http") else domain
    async with httpx.AsyncClient(timeout=10) as client:
        for path in ["/contact", "/about", "/team", "/"]:
            try:
                resp = await client.get(
                    f"{base}{path}",
                    headers={"User-Agent": "FactoryBot/1.0"},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    emails = _extract_emails_from_html(resp.text)
                    if emails:
                        return {"email": emails[0], "source": "website_scrape", "all_emails": emails}
            except Exception:
                continue
    return None


async def _waterfall_enrich(name: str, company: str, domain: str | None) -> tuple[dict | None, list[str]]:
    """Run waterfall enrichment: Apollo → Hunter → website scrape.

    Returns (enrichment_data, sources_used).
    Stops as soon as a verified email is found.
    """
    sources_used = []

    # 1. Apollo
    result = await apollo.enrich_person(name=name, company=company, domain=domain)
    if result and result.get("email"):
        sources_used.append("apollo")
        return result, sources_used

    # 2. Hunter (needs domain)
    if domain:
        parts = name.split(" ", 1)
        first = parts[0] if parts else None
        last = parts[1] if len(parts) > 1 else None
        result = await hunter.find_email(domain=domain, first_name=first, last_name=last)
        if result and result.get("email"):
            sources_used.append("hunter")
            return result, sources_used

    # 3. Website scrape
    if domain:
        result = await _scrape_website_contacts(domain)
        if result and result.get("email"):
            sources_used.append("website_scrape")
            return result, sources_used

    return None, sources_used


def compute_lead_score(
    *,
    icp_config: dict,
    lead: dict,
    has_signal: bool = False,
    signal_age_days: int | None = None,
    email_verified: bool = False,
    has_phone: bool = False,
    has_website: bool = True,
) -> int:
    """Score a lead 0-100 based on ICP match, signals, contact quality, tech stack.

    Scoring breakdown:
    - ICP match (NAICS, size, geo, language) — 40 pts max
    - Signal recency (buying signal in last 30 days) — 30 pts max
    - Contact quality (verified email + phone) — 15 pts max
    - Tech stack match (no website = manual process = high intent) — 15 pts max
    """
    score = 0

    # ICP match — 40 pts
    lead_province = (lead.get("province") or "").upper()
    icp_geo = (icp_config.get("geo") or "").upper()
    if lead_province and icp_geo and lead_province == icp_geo:
        score += 15
    elif not lead_province:
        score += 5  # unknown geo, partial credit

    lead_lang = lead.get("language", "")
    icp_lang = icp_config.get("language", "")
    if lead_lang and icp_lang and lead_lang == icp_lang:
        score += 10

    # Company/niche match heuristic
    score += 15  # base ICP match (lead was sourced from ICP-targeted query)

    # Signal recency — 30 pts
    if has_signal:
        if signal_age_days is not None and signal_age_days <= 7:
            score += 30
        elif signal_age_days is not None and signal_age_days <= 30:
            score += 20
        else:
            score += 10

    # Contact quality — 15 pts
    if email_verified:
        score += 10
    if has_phone:
        score += 5

    # Tech stack — 15 pts (no website = likely manual = high intent)
    if not has_website:
        score += 15
    else:
        score += 5  # has website, some tech adoption

    return min(100, max(0, score))


class EnrichmentAgent(BaseAgent):
    """Waterfall enrichment + scoring for new leads."""

    agent_name = "enrichment_agent"
    default_model = "haiku"

    async def enrich_leads(self, context) -> dict:
        """Enrich all leads with status 'new' across active businesses."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            if business_id:
                query = text(
                    "SELECT id, business_id, name, company, phone, enrichment_data "
                    "FROM leads WHERE business_id = :biz AND status = 'new' "
                    "AND (email IS NULL OR email = '') "
                    "ORDER BY created_at DESC LIMIT 100"
                )
                rows = (await db.execute(query, {"biz": business_id})).fetchall()
            else:
                query = text(
                    "SELECT id, business_id, name, company, phone, enrichment_data "
                    "FROM leads WHERE status = 'new' "
                    "AND (email IS NULL OR email = '') "
                    "ORDER BY created_at DESC LIMIT 200"
                )
                rows = (await db.execute(query)).fetchall()

        if not rows:
            return {"enriched": 0, "verified": 0}

        enriched_count = 0
        verified_count = 0

        for lead in rows:
            enrichment = json.loads(lead.enrichment_data) if lead.enrichment_data else {}
            domain = enrichment.get("website", "")
            if domain and domain.startswith("http"):
                from urllib.parse import urlparse
                domain = urlparse(domain).netloc

            # Waterfall enrichment
            result, sources = await _waterfall_enrich(
                name=lead.name or "",
                company=lead.company or "",
                domain=domain,
            )

            email = result.get("email") if result else None
            phone = result.get("phone") or lead.phone

            # Verify email with ZeroBounce
            email_verified = False
            if email:
                verification = await zerobounce.verify_email(email)
                email_verified = verification.get("status") == "valid"
                if not email_verified:
                    logger.info("email_rejected", email=email, status=verification.get("status"))
                    email = None  # don't use unverified

            # Load playbook for scoring
            playbook = await load_playbook(lead.business_id)
            icp_config = playbook.get("icp", {}) if playbook else {}

            # Check for recent signals
            async with SessionLocal() as db:
                signal_row = (
                    await db.execute(
                        text(
                            "SELECT weight, detected_at FROM signals "
                            "WHERE lead_id = :lid ORDER BY detected_at DESC LIMIT 1"
                        ),
                        {"lid": lead.id},
                    )
                ).fetchone()

            has_signal = signal_row is not None
            signal_age = None
            if signal_row and signal_row.detected_at:
                from datetime import datetime, timezone
                signal_age = (datetime.now(tz=timezone.utc) - signal_row.detected_at).days

            score = compute_lead_score(
                icp_config=icp_config,
                lead={"province": enrichment.get("province"), "language": enrichment.get("language")},
                has_signal=has_signal,
                signal_age_days=signal_age,
                email_verified=email_verified,
                has_phone=bool(phone),
                has_website=bool(domain),
            )

            # Merge enrichment data
            if result:
                enrichment.update(result)
            enrichment["enrichment_sources"] = sources

            async with SessionLocal() as db:
                await db.execute(
                    text(
                        "UPDATE leads SET "
                        "email = COALESCE(:email, email), "
                        "phone = COALESCE(:phone, phone), "
                        "score = :score, "
                        "enrichment_data = :enrich, "
                        "enrichment_sources = :sources::text[], "
                        "status = 'enriched' "
                        "WHERE id = :id"
                    ),
                    {
                        "email": email,
                        "phone": phone,
                        "score": score,
                        "enrich": json.dumps(enrichment),
                        "sources": sources,
                        "id": lead.id,
                    },
                )
                await db.commit()

            enriched_count += 1
            if email_verified:
                verified_count += 1

        await self.log_execution(
            action="enrich_leads",
            result={"enriched": enriched_count, "verified": verified_count},
            business_id=business_id,
        )

        return {"enriched": enriched_count, "verified": verified_count}


def register(hatchet_instance):
    agent = EnrichmentAgent()
    wf = hatchet_instance.workflow(name="enrichment-agent", on_crons=["0 12 * * *"])

    @wf.task(execution_timeout="25m", retries=1)
    async def enrich_leads(input, ctx):
        return await agent.enrich_leads(ctx)

    return wf

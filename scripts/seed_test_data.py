"""Seed the factory database with sample data for testing.

Run with: python -m scripts.seed_test_data

Idempotent: skips if business 'toituro' already exists.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from sqlalchemy import text

from src.db import SessionLocal


# ── Sample data ───────────────────────────────────────────────────────────────

IDEA = {
    "name": "Quote OS",
    "niche": "couvreur toiture",
    "us_equivalent": "JobNimbus",
    "us_equivalent_url": "https://jobnimbus.com",
    "ca_gap_analysis": "No Quebec-focused quote software for roofers.",
    "score": 8.5,
    "status": "validated",
}

BUSINESS = {
    "name": "Toîturo",
    "slug": "toituro",
    "domain": "toituro.ca",
    "niche": "couvreur toiture",
    "status": "live",
    "mrr": 490,
    "customers_count": 10,
}

GTM_PLAYBOOK_CONFIG = {
    "icp": {
        "naics_codes": ["238160"],
        "company_size": "1-25 employees",
        "decision_maker_titles": ["owner", "président", "estimateur"],
        "geo": "QC",
        "language": "fr",
        "tech_signals": ["no_website", "facebook_only", "spreadsheet_user"],
        "pain_keywords": ["estimation longue", "soumission perdue", "calcul erreur"],
    },
    "channels": {
        "primary": "cold_email",
        "secondary": "facebook_groups",
        "tertiary": "association_partnership",
    },
    "channels_ranked": [
        {"channel": "cold_email", "ice": 216, "status": "active"},
        {"channel": "facebook_groups", "ice": 180, "status": "active"},
        {"channel": "association", "ice": 168, "status": "pending_outreach"},
        {"channel": "reddit", "ice": 72, "status": "deprioritized"},
    ],
    "lead_sources": [
        {"type": "google_maps", "query": "couvreur toiture", "geo": "QC", "priority": 1},
        {"type": "rbq_registry", "licence_type": "couvreur", "priority": 2},
        {"type": "association_directory", "org": "AMCQ", "url": "amcq.qc.ca/membres/", "priority": 3},
        {"type": "req_registry", "naics": "238160", "priority": 4},
    ],
    "signals": [
        {"type": "new_business_registration", "source": "req_registry", "weight": 9},
        {"type": "building_permit_issued", "source": "municipal_data", "weight": 8},
        {"type": "competitor_complaint", "source": "google_reviews", "weight": 7},
        {"type": "hiring_estimator", "source": "indeed_scrape", "weight": 6},
        {"type": "website_visit", "source": "plausible", "weight": 10},
    ],
    "messaging": {
        "value_prop_fr": "Créez des soumissions professionnelles en 5 minutes, pas 2 heures",
        "value_prop_en": "Create professional quotes in 5 minutes, not 2 hours",
        "pain_points": ["manual estimation takes too long", "errors cost money", "unprofessional-looking quotes"],
        "proof_points": ["X devis créés", "Y heures économisées"],
        "tone": "direct, tutoiement, québécois authentique",
        "frameworks": ["pain_agitate_solve", "before_after_bridge"],
    },
    "outreach": {
        "email_templates": 4,
        "sequence_days": [0, 3, 7, 12],
        "max_daily_emails": 50,
        "voice_trigger": "replied_positive",
        "cadence": "email → email → email+loom → breakup",
    },
    "referral": {
        "incentive": "1_month_free",
        "ask_trigger": "nps_9_or_10",
        "program_type": "double_sided",
    },
    "go_nogo": "go",
    "confidence": 0.85,
}

LEADS = [
    {"name": "Jean Tremblay", "email": "jean@toitureabc.ca", "company": "Toiture ABC", "phone": "+15145551111", "status": "new"},
    {"name": "Marie Gagnon", "email": "marie@couvreurpro.ca", "company": "Couvreur Pro", "phone": "+15145552222", "status": "enriched"},
    {"name": "Pierre Lavoie", "email": "pierre@toitmontreal.ca", "company": "Toit Montréal", "phone": "+15145553333", "status": "contacted"},
    {"name": "Sophie Bouchard", "email": "sophie@roofquebec.ca", "company": "Roof Québec", "phone": "+15145554444", "status": "replied"},
    {"name": "Luc Martin", "email": "luc@martintoiture.ca", "company": "Martin Toiture", "phone": "+15145555555", "status": "converted"},
]

CUSTOMERS = [
    {"name": "André Dubois", "email": "andre@test1.ca", "status": "trial", "plan": "premium"},
    {"name": "Claire Roy", "email": "claire@test2.ca", "status": "active", "plan": "premium"},
    {"name": "François Bergeron", "email": "francois@test3.ca", "status": "churned", "plan": "free"},
]

AGENT_LOGS = [
    ("idea_factory", "discover_ideas", 0.02),
    ("deep_scout", "research_market", 0.15),
    ("validator", "evaluate_results", 0.01),
    ("brand_designer", "quick_brand", 0.03),
    ("builder", "generate_code", 0.25),
    ("lead_pipeline", "generate_leads", 0.01),
    ("enrichment_agent", "enrich_leads", 0.05),
    ("outreach_agent", "run_outreach", 0.02),
    ("reply_handler", "classify_reply", 0.01),
    ("analytics_agent", "compute_snapshot", 0.08),
]

CONTENT_POSTS = [
    {"title": "Comment faire une soumission de toiture en 5 étapes", "slug": "soumission-toiture-5-etapes", "type": "blog_fr"},
    {"title": "5 Tips for Faster Roofing Estimates", "slug": "5-tips-faster-roofing-estimates", "type": "blog_en"},
]


async def seed() -> None:
    async with SessionLocal() as db:
        # Idempotency: skip if toituro already exists
        existing = (
            await db.execute(
                text("SELECT id FROM businesses WHERE slug = :slug"),
                {"slug": BUSINESS["slug"]},
            )
        ).fetchone()
        if existing:
            print("Data already seeded (business 'toituro' exists). Skipping.")
            return

        # 1. Create idea
        idea_row = (
            await db.execute(
                text(
                    "INSERT INTO ideas (name, niche, us_equivalent, us_equivalent_url, ca_gap_analysis, "
                    "score, status, created_at, updated_at) "
                    "VALUES (:name, :niche, :us_eq, :us_url, :gap, :score, :status, NOW(), NOW()) "
                    "RETURNING id"
                ),
                {
                    "name": IDEA["name"],
                    "niche": IDEA["niche"],
                    "us_eq": IDEA["us_equivalent"],
                    "us_url": IDEA["us_equivalent_url"],
                    "gap": IDEA["ca_gap_analysis"],
                    "score": IDEA["score"],
                    "status": IDEA["status"],
                },
            )
        ).fetchone()
        idea_id = idea_row.id
        print(f"  Created idea: {IDEA['name']} (id={idea_id})")

        # 2. Create business
        biz_row = (
            await db.execute(
                text(
                    "INSERT INTO businesses (idea_id, name, slug, domain, niche, status, mrr, "
                    "customers_count, created_at, updated_at) "
                    "VALUES (:idea_id, :name, :slug, :domain, :niche, :status, :mrr, :cust, NOW(), NOW()) "
                    "RETURNING id"
                ),
                {
                    "idea_id": idea_id,
                    "name": BUSINESS["name"],
                    "slug": BUSINESS["slug"],
                    "domain": BUSINESS["domain"],
                    "niche": BUSINESS["niche"],
                    "status": BUSINESS["status"],
                    "mrr": BUSINESS["mrr"],
                    "cust": BUSINESS["customers_count"],
                },
            )
        ).fetchone()
        business_id = biz_row.id
        print(f"  Created business: {BUSINESS['name']} (id={business_id})")

        # 3. Create GTM playbook
        await db.execute(
            text(
                "INSERT INTO gtm_playbooks (business_id, config, version, last_updated_by, created_at, updated_at) "
                "VALUES (:biz, :config::jsonb, 1, 'seed_test_data', NOW(), NOW()) "
                "ON CONFLICT (business_id) DO UPDATE SET config = EXCLUDED.config, updated_at = NOW()"
            ),
            {"biz": business_id, "config": json.dumps(GTM_PLAYBOOK_CONFIG)},
        )
        print(f"  Created GTM playbook for business {business_id}")

        # 4. Create leads
        for lead in LEADS:
            await db.execute(
                text(
                    "INSERT INTO leads (business_id, name, email, company, phone, source, consent_type, status) "
                    "VALUES (:biz, :name, :email, :company, :phone, 'google_maps', 'conspicuous_publication', :status)"
                ),
                {
                    "biz": business_id,
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "phone": lead["phone"],
                    "status": lead["status"],
                },
            )
        print(f"  Created {len(LEADS)} leads")

        # 5. Create customers
        for cust in CUSTOMERS:
            await db.execute(
                text(
                    "INSERT INTO customers (business_id, name, email, status, plan, language) "
                    "VALUES (:biz, :name, :email, :status, :plan, 'fr')"
                ),
                {
                    "biz": business_id,
                    "name": cust["name"],
                    "email": cust["email"],
                    "status": cust["status"],
                    "plan": cust["plan"],
                },
            )
        print(f"  Created {len(CUSTOMERS)} customers")

        # 6. Create agent_logs
        for agent_name, action, cost in AGENT_LOGS:
            await db.execute(
                text(
                    "INSERT INTO agent_logs (agent_name, business_id, action, result, cost_usd, status) "
                    "VALUES (:name, :biz, :action, '{}'::jsonb, :cost, 'success')"
                ),
                {"name": agent_name, "biz": business_id, "action": action, "cost": cost},
            )
        print(f"  Created {len(AGENT_LOGS)} agent_logs entries")

        # 7. Create daily_snapshot
        today = date.today()
        await db.execute(
            text(
                "INSERT INTO daily_snapshots (business_id, date, mrr, customers_active, customers_new, "
                "customers_churned, leads_new, leads_converted, kill_score, api_cost_usd) "
                "VALUES (:biz, :dt, :mrr, :cust_active, :cust_new, :cust_churned, :leads_new, :leads_conv, :kill, :api) "
                "ON CONFLICT (business_id, date) DO UPDATE SET "
                "mrr = EXCLUDED.mrr, customers_active = EXCLUDED.customers_active, "
                "kill_score = EXCLUDED.kill_score, api_cost_usd = EXCLUDED.api_cost_usd"
            ),
            {
                "biz": business_id,
                "dt": today,
                "mrr": BUSINESS["mrr"],
                "cust_active": 8,
                "cust_new": 2,
                "cust_churned": 1,
                "leads_new": 3,
                "leads_conv": 1,
                "kill": 72.5,
                "api": 0.63,
            },
        )
        print(f"  Created daily_snapshot for {today}")

        # 8. Create content (blog posts)
        for post in CONTENT_POSTS:
            await db.execute(
                text(
                    "INSERT INTO content (business_id, type, title, slug, body, status) "
                    "VALUES (:biz, :type, :title, :slug, :body, 'published')"
                ),
                {
                    "biz": business_id,
                    "type": post["type"],
                    "title": post["title"],
                    "slug": post["slug"],
                    "body": f"Sample content for {post['title']}.",
                },
            )
        print(f"  Created {len(CONTENT_POSTS)} content entries")

        await db.commit()

    # Summary
    print("\n" + "=" * 60)
    print("SEED COMPLETE — Summary")
    print("=" * 60)
    print(f"  Idea:        {IDEA['name']} (score={IDEA['score']}, status={IDEA['status']})")
    print(f"  Business:    {BUSINESS['name']} (slug={BUSINESS['slug']}, mrr=${BUSINESS['mrr']}, customers={BUSINESS['customers_count']})")
    print(f"  GTM:        Full config (icp, channels_ranked, lead_sources, signals, messaging, outreach, referral)")
    print(f"  Leads:      {len(LEADS)} (new, enriched, contacted, replied, converted)")
    print(f"  Customers:  {len(CUSTOMERS)} (trial, active, churned)")
    print(f"  Agent logs: {len(AGENT_LOGS)} entries")
    print(f"  Snapshot:   1 daily_snapshot")
    print(f"  Content:    {len(CONTENT_POSTS)} blog posts")
    print("=" * 60)


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()

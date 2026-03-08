"""Agent 9: Content Engine.

Cron Mon + Thu 7 AM + after new business launch.  Two modes:

EDITORIAL — 3-5 articles/week in both FR and EN (not translations — different
keywords per language).  Every article has a "Quick Answer" section for GEO
(LLM-optimized content).

PROGRAMMATIC SEO — generate templated pages at scale from database.  Universal
templates that work across all verticals:
  [Product] for [sub-vertical]
  [Product] vs [Competitor]
  Best [category] software in [province]
  [Product] + [Integration]
  How to [workflow] in [province]
  [Industry] [metric] Canada [year]

Reads keywords and ICP from gtm_playbooks config.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses, load_playbook
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

EDITORIAL_SYSTEM_PROMPT = """\
Tu es le Content Engine. Tu écris des articles de blog SEO pour un SaaS canadien.

RÈGLES:
- Commence par une section "Quick Answer" (2-3 phrases que un LLM citerait directement)
- Inclus des données chiffrées et spécifiques (les LLMs citent les chiffres, pas le vague)
- Cible des mots-clés en format question: "Comment faire X au Québec?"
- Assure que le nom du produit + niche + "Canada" apparaissent naturellement
- Article de 800-1200 mots
- Ton professionnel mais accessible
- Termine avec un CTA subtil vers le produit

Réponds en Markdown avec frontmatter YAML (title, description, keywords, slug).
"""

PROGRAMMATIC_SYSTEM_PROMPT = """\
Tu génères une page SEO programmatique pour un SaaS canadien.

Tu reçois: le template type, les variables, et le contexte business.

La page doit:
- Avoir 300-500 mots (pas un stub, pas un roman)
- Section "Quick Answer" au début
- Données spécifiques (prix, nombre d'entreprises, réglementations)
- Mots-clés naturellement intégrés
- CTA vers le produit
- Bilingue selon la langue demandée

Réponds en Markdown avec frontmatter YAML (title, description, keywords, slug, template_type).
"""

PROGRAMMATIC_TEMPLATES = [
    {
        "type": "product_for_subvertical",
        "pattern_fr": "{product} pour {subvertical}",
        "pattern_en": "{product} for {subvertical}",
    },
    {
        "type": "product_vs_competitor",
        "pattern_fr": "{product} vs {competitor}",
        "pattern_en": "{product} vs {competitor}",
    },
    {
        "type": "best_category_in_province",
        "pattern_fr": "Meilleur {category} au {province}",
        "pattern_en": "Best {category} in {province}",
    },
    {
        "type": "product_plus_integration",
        "pattern_fr": "{product} + {integration}",
        "pattern_en": "{product} + {integration}",
    },
    {
        "type": "how_to_workflow",
        "pattern_fr": "Comment {workflow} au Québec",
        "pattern_en": "How to {workflow} in {province}",
    },
    {
        "type": "industry_metric_year",
        "pattern_fr": "{metric} au Canada — {year}",
        "pattern_en": "{metric} in Canada — {year}",
    },
]

PROVINCES_FR = ["Québec", "Ontario", "Colombie-Britannique", "Alberta"]
PROVINCES_EN = ["Quebec", "Ontario", "British Columbia", "Alberta"]


def generate_programmatic_variants(
    *,
    product_name: str,
    niche: str,
    sub_verticals: list[str],
    competitors: list[str],
    integrations: list[str],
    workflows: list[str],
    metrics: list[str],
) -> list[dict]:
    """Generate all programmatic page variants from templates and variable lists."""
    year = datetime.now(tz=timezone.utc).year
    variants = []

    for sv in sub_verticals:
        variants.append({
            "type": "product_for_subvertical",
            "vars": {"product": product_name, "subvertical": sv},
            "languages": ["fr", "en"],
        })

    for comp in competitors:
        variants.append({
            "type": "product_vs_competitor",
            "vars": {"product": product_name, "competitor": comp},
            "languages": ["fr", "en"],
        })

    for prov_fr, prov_en in zip(PROVINCES_FR, PROVINCES_EN):
        variants.append({
            "type": "best_category_in_province",
            "vars": {"category": niche, "province": prov_fr, "province_en": prov_en},
            "languages": ["fr", "en"],
        })

    for integ in integrations:
        variants.append({
            "type": "product_plus_integration",
            "vars": {"product": product_name, "integration": integ},
            "languages": ["fr", "en"],
        })

    for wf in workflows:
        variants.append({
            "type": "how_to_workflow",
            "vars": {"workflow": wf, "province": "Quebec"},
            "languages": ["fr", "en"],
        })

    for metric in metrics:
        variants.append({
            "type": "industry_metric_year",
            "vars": {"metric": metric, "year": str(year)},
            "languages": ["fr", "en"],
        })

    return variants


class ContentEngine(BaseAgent):
    """SEO content engine — editorial articles + programmatic pages at scale."""

    agent_name = "content_engine"
    default_model = "sonnet"

    async def editorial_content(self, context) -> dict:
        """Write 1-2 editorial articles (FR + EN) per business."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"articles_written": 0}

        total_articles = 0
        total_cost = 0.0

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            messaging = playbook.get("messaging", {})
            keywords_fr = playbook.get("top_keywords_fr", [])
            keywords_en = playbook.get("top_keywords_en", [])
            icp = playbook.get("icp", {})

            for lang, keywords in [("fr", keywords_fr), ("en", keywords_en)]:
                if not keywords:
                    continue
                target_keyword = keywords[0] if keywords else f"{biz['name']} {icp.get('geo', 'Canada')}"

                model_tier = await self.check_budget()
                user_prompt = json.dumps({
                    "business_name": biz["name"],
                    "niche": biz.get("slug", ""),
                    "keyword": target_keyword,
                    "language": lang,
                    "value_prop": messaging.get(f"value_prop_{lang}", ""),
                    "icp": icp,
                    "domain": biz.get("domain", ""),
                }, default=str)

                article_md, cost = await call_claude(
                    model_tier=model_tier,
                    system=EDITORIAL_SYSTEM_PROMPT,
                    user=user_prompt,
                    max_tokens=4096,
                    temperature=0.5,
                )
                total_cost += cost

                # Persist to content table
                content_type = f"blog_{lang}"
                slug = target_keyword.lower().replace(" ", "-")[:80]

                async with SessionLocal() as db:
                    await db.execute(
                        text(
                            "INSERT INTO content (business_id, type, title, slug, body, "
                            "keywords, status, published_at) "
                            "VALUES (:biz, :type, :title, :slug, :body, :kw, 'draft', NOW())"
                        ),
                        {
                            "biz": biz["id"],
                            "type": content_type,
                            "title": target_keyword,
                            "slug": slug,
                            "body": article_md,
                            "kw": keywords[:5],
                        },
                    )
                    await db.commit()

                total_articles += 1

            await self.log_execution(
                action="editorial_content",
                result={"articles": total_articles},
                cost_usd=total_cost,
                business_id=biz["id"],
            )

        return {"articles_written": total_articles, "cost_usd": total_cost}

    async def programmatic_seo(self, context) -> dict:
        """Generate templated SEO pages at scale — 20-50 per business at launch."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"pages_generated": 0}

        total_pages = 0
        total_cost = 0.0

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            icp = playbook.get("icp", {})
            messaging = playbook.get("messaging", {})
            ecosystems = playbook.get("ecosystems", [])

            # Extract variables from playbook
            pain_keywords = icp.get("pain_keywords", [])
            integrations = [e.get("platform", "") for e in ecosystems if e.get("platform")]

            # Sub-verticals: derive from NAICS or playbook
            sub_verticals = icp.get("sub_verticals", ["couvreurs", "plombiers", "électriciens"])
            competitors = playbook.get("competitors", [])
            workflows = pain_keywords[:3] if pain_keywords else ["estimer un projet"]
            metrics = [f"Coûts moyens de {icp.get('niche', 'construction')} par ville"]

            variants = generate_programmatic_variants(
                product_name=biz["name"],
                niche=biz.get("slug", ""),
                sub_verticals=sub_verticals,
                competitors=competitors,
                integrations=integrations,
                workflows=workflows,
                metrics=metrics,
            )

            for variant in variants:
                for lang in variant.get("languages", ["fr"]):
                    model_tier = await self.check_budget()

                    tmpl = next(
                        (t for t in PROGRAMMATIC_TEMPLATES if t["type"] == variant["type"]),
                        None,
                    )
                    pattern = tmpl.get(f"pattern_{lang}", "") if tmpl else ""
                    try:
                        title = pattern.format(**variant["vars"])
                    except KeyError:
                        title = f"{biz['name']} - {variant['type']}"

                    user_prompt = json.dumps({
                        "template_type": variant["type"],
                        "title": title,
                        "variables": variant["vars"],
                        "language": lang,
                        "business_name": biz["name"],
                        "niche": biz.get("slug", ""),
                        "domain": biz.get("domain", ""),
                    }, default=str)

                    page_md, cost = await call_claude(
                        model_tier=model_tier,
                        system=PROGRAMMATIC_SYSTEM_PROMPT,
                        user=user_prompt,
                        max_tokens=2048,
                        temperature=0.3,
                    )
                    total_cost += cost

                    slug = title.lower().replace(" ", "-").replace("'", "")[:100]
                    async with SessionLocal() as db:
                        await db.execute(
                            text(
                                "INSERT INTO content (business_id, type, title, slug, body, "
                                "keywords, status, published_at) "
                                "VALUES (:biz, 'landing_page', :title, :slug, :body, :kw, 'draft', NOW()) "
                                "ON CONFLICT DO NOTHING"
                            ),
                            {
                                "biz": biz["id"],
                                "title": title,
                                "slug": slug,
                                "body": page_md,
                                "kw": [title],
                            },
                        )
                        await db.commit()

                    total_pages += 1

            await self.log_execution(
                action="programmatic_seo",
                result={"pages": total_pages},
                cost_usd=total_cost,
                business_id=biz["id"],
            )

        return {"pages_generated": total_pages, "cost_usd": total_cost}

    async def regenerate_llms_txt(self, context) -> dict:
        """After each publish, regenerate /llms-full.txt for the business site."""
        businesses = await get_active_businesses()
        updated = 0

        for biz in businesses:
            github_repo = None
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        text("SELECT github_repo FROM businesses WHERE id = :id"),
                        {"id": biz["id"]},
                    )
                ).fetchone()
                github_repo = row.github_repo if row else None

            if not github_repo:
                continue

            # Gather all published content for this business
            async with SessionLocal() as db:
                articles = (
                    await db.execute(
                        text(
                            "SELECT title, slug, body FROM content "
                            "WHERE business_id = :biz AND status IN ('draft', 'published') "
                            "ORDER BY created_at DESC LIMIT 100"
                        ),
                        {"biz": biz["id"]},
                    )
                ).fetchall()

            if not articles:
                continue

            llms_full = f"# {biz['name']} — Complete Content\n\n"
            for a in articles:
                llms_full += f"## {a.title}\n\n{a.body}\n\n---\n\n"

            # Push to GitHub
            async with httpx.AsyncClient(timeout=15) as client:
                try:
                    import base64
                    encoded = base64.b64encode(llms_full.encode()).decode()

                    # Check if file exists to get SHA
                    existing = await client.get(
                        f"https://api.github.com/repos/{github_repo}/contents/public/llms-full.txt",
                        headers={
                            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                            "Accept": "application/vnd.github+json",
                        },
                    )
                    sha = existing.json().get("sha") if existing.status_code == 200 else None

                    payload = {
                        "message": "chore: regenerate llms-full.txt",
                        "content": encoded,
                    }
                    if sha:
                        payload["sha"] = sha

                    await client.put(
                        f"https://api.github.com/repos/{github_repo}/contents/public/llms-full.txt",
                        headers={
                            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                            "Accept": "application/vnd.github+json",
                        },
                        json=payload,
                    )
                    updated += 1
                except Exception as exc:
                    logger.warning("llms_txt_push_failed", repo=github_repo, error=str(exc))

        return {"llms_txt_updated": updated}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="content-engine", on_crons=["0 12 * * 1,4"])
    class _Registered(ContentEngine):
        @hatchet_instance.task(execution_timeout="20m", retries=1)
        async def editorial_content(self, context: Context) -> dict:
            return await ContentEngine.editorial_content(self, context)

        @hatchet_instance.task(execution_timeout="20m", retries=1)
        async def programmatic_seo(self, context: Context) -> dict:
            return await ContentEngine.programmatic_seo(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def regenerate_llms_txt(self, context: Context) -> dict:
            return await ContentEngine.regenerate_llms_txt(self, context)

    return _Registered

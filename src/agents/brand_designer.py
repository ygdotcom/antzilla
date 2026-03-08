"""Agent 5: Brand Designer.

Two modes:
- LIGHT: pre-validation quick brand (colors, fonts, tone, 2 name options + domain check).
- FULL:  pre-build comprehensive brand kit (research inspiration, generate full kit, save).

Uses Claude Opus for creative + analytical work.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.integrations import namecheap
from src.llm import call_claude

logger = structlog.get_logger()

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "brand_designer.txt"

COLD_EMAIL_TLDS = [".io", ".co"]


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _parse_brand_kit(response_text: str) -> dict | None:
    """Parse Claude's JSON brand kit response."""
    text_clean = response_text.strip()
    if text_clean.startswith("```"):
        lines = text_clean.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text_clean = "\n".join(lines)

    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        start = text_clean.find("{")
        end = text_clean.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text_clean[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.error("brand_kit_parse_failed", raw=text_clean[:500])
    return None


def _validate_brand_kit(kit: dict) -> list[str]:
    """Return missing required top-level keys."""
    required = ["colors", "typography", "tone"]
    return [k for k in required if k not in kit]


def _generate_domain_variants(name: str) -> list[str]:
    """Generate .ca, .com, .io, .co domain variants for a name."""
    slug = name.lower().replace(" ", "").replace("'", "").replace("î", "i").replace("é", "e")
    return [f"{slug}{tld}" for tld in [".ca", ".com", ".io", ".co"]]


class BrandDesigner(BaseAgent):
    """Brand identity agent — light mode for validation, full mode for build."""

    agent_name = "brand_designer"
    default_model = "opus"

    # ── LIGHT MODE (single step) ─────────────────────────────────────────

    async def quick_brand(self, context) -> dict:
        """Light mode: quick brand kit for pre-validation landing page."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        scout_report = input_data.get("scout_report", "")
        niche = input_data.get("niche", "")

        model_tier = await self.check_budget()
        system_prompt = _load_prompt()

        user_msg = (
            f"MODE: LIGHT (pre-validation, quick brand)\n\n"
            f"Niche: {niche}\n\n"
            f"Scout Report (branding section):\n{scout_report[:5000]}\n\n"
            f"Produis un brand kit LIGHT: 2 name options, couleurs principales, "
            f"typographie, ton FR/EN. Pas besoin de mood board ni competitor_inspiration détaillé."
        )

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=user_msg,
            max_tokens=4096,
            temperature=0.5,
        )

        kit = _parse_brand_kit(response_text)

        # Check domains for name options
        if kit and kit.get("name_options"):
            all_domains = []
            for opt in kit["name_options"]:
                variants = _generate_domain_variants(opt.get("name", ""))
                all_domains.extend(variants)
            if all_domains:
                checks = await namecheap.check_domains_batch(all_domains)
                avail_map = {c["domain"]: c.get("available", False) for c in checks}
                for opt in kit["name_options"]:
                    slug = opt.get("name", "").lower().replace(" ", "").replace("'", "").replace("î", "i").replace("é", "e")
                    opt["domain_ca"] = "available" if avail_map.get(f"{slug}.ca") else "taken"
                    opt["domain_com"] = "available" if avail_map.get(f"{slug}.com") else "taken"

        # Save light brand kit
        if kit and business_id:
            async with SessionLocal() as db:
                await db.execute(
                    text("UPDATE businesses SET brand_kit = :kit, updated_at = NOW() WHERE id = :id"),
                    {"kit": json.dumps(kit), "id": business_id},
                )
                await db.commit()

        await self.log_execution(
            action="quick_brand",
            result={"has_kit": kit is not None, "name_options": len(kit.get("name_options", [])) if kit else 0},
            cost_usd=cost,
            business_id=business_id,
        )

        return {"brand_kit": kit, "mode": "light", "cost_usd": cost}

    # ── FULL MODE (multi-step) ───────────────────────────────────────────

    async def research_inspiration(self, context) -> dict:
        """Full mode step 1: Scrape competitor and design inspiration sites."""
        input_data = context.workflow_input()
        scout_report = input_data.get("scout_report", "")
        us_url = input_data.get("us_equivalent_url", "")
        niche = input_data.get("niche", "")

        pages = {}
        async with httpx.AsyncClient(timeout=15) as client:
            if us_url:
                try:
                    resp = await client.get(
                        us_url,
                        headers={"User-Agent": "FactoryBot/1.0"},
                        follow_redirects=True,
                    )
                    pages["us_competitor"] = resp.text[:8000]
                except Exception:
                    pages["us_competitor"] = "[scrape failed]"

            for query in [f"{niche} SaaS design", "best SaaS landing pages 2026"]:
                try:
                    resp = await client.get(
                        "https://www.google.ca/search",
                        params={"q": f"site:dribbble.com {query}", "num": 5},
                        headers={"User-Agent": "FactoryBot/1.0"},
                        follow_redirects=True,
                    )
                    pages[f"dribbble_{query[:20]}"] = resp.text[:3000]
                except Exception:
                    pass

        return {
            "inspiration_pages": pages,
            "scout_report_excerpt": scout_report[:5000],
            "us_url": us_url,
            "niche": niche,
        }

    async def generate_brand_kit(self, context) -> dict:
        """Full mode step 2: Generate comprehensive brand kit via Claude Opus."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        inspiration = context.step_output("research_inspiration")

        model_tier = await self.check_budget()
        system_prompt = _load_prompt()

        user_msg = (
            f"MODE: FULL (pre-build, comprehensive brand kit)\n\n"
            f"Niche: {inspiration.get('niche', '')}\n\n"
            f"Scout Report:\n{inspiration.get('scout_report_excerpt', '')}\n\n"
            f"US Competitor site content:\n{json.dumps(inspiration.get('inspiration_pages', {}), default=str)[:8000]}\n\n"
            f"Produis le brand kit COMPLET avec toutes les sections."
        )

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=user_msg,
            max_tokens=4096,
            temperature=0.5,
        )

        kit = _parse_brand_kit(response_text)

        await self.log_execution(
            action="generate_brand_kit",
            result={"has_kit": kit is not None},
            cost_usd=cost,
            business_id=business_id,
        )

        return {"brand_kit": kit, "cost_usd": cost}

    async def check_domains(self, context) -> dict:
        """Full mode step 3: Check domain availability for all name options."""
        gen = context.step_output("generate_brand_kit")
        kit = gen.get("brand_kit")

        if not kit or not kit.get("name_options"):
            return {"domain_results": [], "brand_kit": kit}

        all_domains = []
        for opt in kit["name_options"]:
            all_domains.extend(_generate_domain_variants(opt.get("name", "")))

        checks = await namecheap.check_domains_batch(all_domains)
        avail_map = {c["domain"]: c.get("available", False) for c in checks}

        for opt in kit["name_options"]:
            slug = opt.get("name", "").lower().replace(" ", "").replace("'", "").replace("î", "i").replace("é", "e")
            opt["domain_ca"] = "available" if avail_map.get(f"{slug}.ca") else "taken"
            opt["domain_com"] = "available" if avail_map.get(f"{slug}.com") else "taken"
            opt["domain_io"] = "available" if avail_map.get(f"{slug}.io") else "taken"
            opt["domain_co"] = "available" if avail_map.get(f"{slug}.co") else "taken"

        return {"domain_results": checks, "brand_kit": kit}

    async def save_brand_kit(self, context) -> dict:
        """Full mode step 4: Persist final brand kit to businesses.brand_kit."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        domains = context.step_output("check_domains")
        kit = domains.get("brand_kit")

        if not kit:
            return {"saved": False, "reason": "no brand kit generated"}

        missing = _validate_brand_kit(kit)
        if missing:
            logger.warning("brand_kit_incomplete", missing=missing)

        if business_id:
            async with SessionLocal() as db:
                await db.execute(
                    text("UPDATE businesses SET brand_kit = :kit, updated_at = NOW() WHERE id = :id"),
                    {"kit": json.dumps(kit), "id": business_id},
                )
                await db.commit()

        await self.log_execution(
            action="save_brand_kit",
            result={
                "business_id": business_id,
                "recommended_name": kit.get("recommended_name"),
                "name_options_count": len(kit.get("name_options", [])),
            },
            business_id=business_id,
        )

        return {"saved": True, "brand_kit": kit, "mode": "full"}


def register(hatchet_instance):
    """Register BrandDesigner with two workflow variants: light and full."""
    agent = BrandDesigner()

    wf_light = hatchet_instance.workflow(name="brand-designer-light")

    @wf_light.task(execution_timeout="8m", retries=2)
    async def quick_brand(input, ctx):
        return await agent.quick_brand(ctx)

    wf_full = hatchet_instance.workflow(name="brand-designer-full")

    @wf_full.task(execution_timeout="5m", retries=2)
    async def research_inspiration(input, ctx):
        return await agent.research_inspiration(ctx)

    @wf_full.task(execution_timeout="8m", retries=2)
    async def generate_brand_kit(input, ctx):
        return await agent.generate_brand_kit(ctx)

    @wf_full.task(execution_timeout="3m", retries=2)
    async def check_domains(input, ctx):
        return await agent.check_domains(ctx)

    @wf_full.task(execution_timeout="3m", retries=1)
    async def save_brand_kit(input, ctx):
        return await agent.save_brand_kit(ctx)

    return wf_light, wf_full

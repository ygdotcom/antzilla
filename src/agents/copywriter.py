"""Agent 30: Copywriter — generates all website text in FR + EN.

Runs after Architecture but before Code Gen. Produces complete messages/fr.json
and messages/en.json with niche-specific, conversion-optimized copy.

The Code Gen step then receives these messages files and uses them in the
generated components via next-intl's useTranslations().
"""

from __future__ import annotations

import json

import structlog

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

COPY_SYSTEM_PROMPT = """\
You are a world-class SaaS copywriter who writes in both French (Quebec) and English.
Your copy converts visitors into paying customers.

You receive: the app architecture (with features, how-it-works, pricing),
the brand kit (tone, name, tagline), and the niche/ICP description.

Produce COMPLETE messages files for next-intl in both languages.
Every single piece of text on the website must come from these files.

COPYWRITING PRINCIPLES:
- Lead with the customer's pain, not the product's features
- Be specific: "Save 4 hours/week on receipt sorting" not "Save time"
- Use numbers and specifics wherever possible
- CTAs should feel low-risk: "Start free" not "Buy now"
- Headlines: max 8 words, address the #1 pain point directly
- Subheadlines: expand on the headline, add credibility
- Feature descriptions: benefit first, then how
- Social proof language: "Trusted by X Canadian businesses"
- French must feel native Quebec French (tu, not vous for SaaS)
- English must feel North American professional, not British

REQUIRED SECTIONS in the messages files:
- common: appName, tagline, loading, save, cancel, delete, back
- nav: dashboard, pricing, blog, login, signup, logout, features
- hero: badge, title, subtitle, demo, noCard
- features: label, title, subtitle, f1_title, f1_desc, f2_title, f2_desc, f3_title, f3_desc
- howItWorks: title, subtitle, step1_title, step1_desc, step2_title, step2_desc, step3_title, step3_desc
- social: trusted
- cta: title, subtitle, check1, check2, check3
- auth: loginTitle, signupTitle, nameLabel, emailLabel, phoneLabel, signupCta, loginCta, noAccount, hasAccount
- dashboard: title, welcomeBack, sampleProject, sampleDescription, createNew, empty, onboarding.*
- pricing: title, subtitle, monthly, annual, freeTier, proTier, businessTier, startTrial, perMonth, features for each tier
- trial: daysLeft, upgradeNow, trialEnded
- referral: title, description, yourCode, share
- legal: privacy, terms
- meta: title, description (for SEO <title> and <meta description>)

Respond ONLY with valid JSON:
{
  "messages_fr": { ... complete fr.json ... },
  "messages_en": { ... complete en.json ... }
}

The copy must be SO good that a visitor thinks "this company really understands my problem."
Every word earns its place. No filler. No corporate speak. No "leverage" or "synergy."
"""


class Copywriter(BaseAgent):
    """Generates bilingual website copy optimized for conversion."""

    agent_name = "copywriter"
    default_model = "sonnet"

    async def generate_copy(self, context) -> dict:
        """Generate complete FR + EN messages files."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        architecture = input_data.get("architecture", {})
        brand_kit = input_data.get("brand_kit", {})
        niche = input_data.get("niche", "")
        scout_report = input_data.get("scout_report", "")

        model_tier = await self.check_budget()

        user_payload = json.dumps({
            "architecture": architecture,
            "brand_kit": brand_kit,
            "niche": niche,
            "scout_report_excerpt": scout_report[:5000] if scout_report else "",
            "app_name": architecture.get("app_name", brand_kit.get("recommended_name", "")),
            "features": architecture.get("features", []),
            "how_it_works": architecture.get("how_it_works", []),
            "pricing": architecture.get("pricing", {}),
            "headline_fr": architecture.get("headline_fr", ""),
            "headline_en": architecture.get("headline_en", ""),
        }, default=str)

        response, cost = await call_claude(
            model_tier=model_tier,
            system=COPY_SYSTEM_PROMPT,
            user=user_payload,
            max_tokens=8192,
            temperature=0.4,
        )

        # Parse the response
        result = None
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            clean = "\n".join(lines)
        try:
            result = json.loads(clean)
        except json.JSONDecodeError:
            start = clean.find("{")
            end = clean.rfind("}")
            if start >= 0 and end > start:
                try:
                    result = json.loads(clean[start:end + 1])
                except json.JSONDecodeError:
                    pass

        messages_fr = {}
        messages_en = {}
        if result:
            messages_fr = result.get("messages_fr", {})
            messages_en = result.get("messages_en", {})

        # Ensure appName is set
        app_name = architecture.get("app_name", brand_kit.get("recommended_name", "App"))
        if messages_fr.get("common"):
            messages_fr["common"]["appName"] = app_name
        if messages_en.get("common"):
            messages_en["common"]["appName"] = app_name

        await self.log_execution(
            action="generate_copy",
            result={
                "fr_keys": len(messages_fr),
                "en_keys": len(messages_en),
                "app_name": app_name,
                "has_hero": bool(messages_fr.get("hero")),
                "has_features": bool(messages_fr.get("features")),
            },
            cost_usd=cost,
            business_id=business_id,
        )

        logger.info("copy_generated",
                     fr_sections=list(messages_fr.keys()),
                     en_sections=list(messages_en.keys()),
                     app_name=app_name)

        return {
            "messages_fr": messages_fr,
            "messages_en": messages_en,
            "app_name": app_name,
            "cost_usd": cost,
        }


def register(hatchet_instance):
    """Register Copywriter as a Hatchet workflow."""
    agent = Copywriter()
    wf = hatchet_instance.workflow(name="copywriter")

    @wf.task(execution_timeout="5m", retries=2)
    async def generate_copy(input, ctx):
        return await agent.generate_copy(ctx)

    return wf

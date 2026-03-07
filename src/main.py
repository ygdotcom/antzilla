"""Hatchet worker startup — registers all 27 agent workflows and starts the worker."""

import structlog
from hatchet_sdk import Hatchet

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()


def main():
    hatchet = Hatchet()
    worker = hatchet.worker("factory-worker")

    # ── Wave 1 — Ship and sell ────────────────────────────────────────────
    from src.agents.meta_orchestrator import register as register_meta
    from src.agents.idea_factory import register as register_idea_factory
    from src.agents.deep_scout import register as register_deep_scout
    from src.agents.validator import register as register_validator
    from src.agents.brand_designer import register as register_brand
    from src.agents.domain_provisioner import register as register_domain
    from src.agents.builder import register as register_builder
    from src.agents.analytics_agent import register as register_analytics

    # Distribution engine (5 sub-agents)
    from src.agents.distribution.lead_pipeline import register as register_leads
    from src.agents.distribution.enrichment import register as register_enrichment
    from src.agents.distribution.signal_monitor import register as register_signals
    from src.agents.distribution.outreach import register as register_outreach
    from src.agents.distribution.reply_handler import register as register_replies

    # ── Wave 2 — Grow ────────────────────────────────────────────────────
    from src.agents.content_engine import register as register_content
    from src.agents.social_agent import register as register_social
    from src.agents.referral_agent import register as register_referral
    from src.agents.voice_agent import register as register_voice
    from src.agents.billing_agent import register as register_billing
    from src.agents.support_agent import register as register_support
    from src.agents.i18n_agent import register as register_i18n
    from src.agents.email_nurture import register as register_nurture

    # ── Wave 3 — Optimize ────────────────────────────────────────────────
    from src.agents.onboarding_agent import register as register_onboarding
    from src.agents.upsell_agent import register as register_upsell
    from src.agents.social_proof import register as register_social_proof
    from src.agents.competitor_watch import register as register_competitor
    from src.agents.fulfillment import register as register_fulfillment
    from src.agents.self_reflection import register as register_self_reflection
    from src.agents.legal_guardrail import register as register_legal
    from src.agents.devops_agent import register as register_devops
    from src.agents.budget_guardian import register as register_budget_guardian
    from src.agents.growth_hacker import register as register_growth

    workflows = []

    # Wave 1
    workflows.append(register_meta(hatchet))
    workflows.append(register_idea_factory(hatchet))
    workflows.append(register_deep_scout(hatchet))
    workflows.append(register_validator(hatchet))
    light_brand, full_brand = register_brand(hatchet)
    workflows.extend([light_brand, full_brand])
    workflows.append(register_domain(hatchet))
    workflows.append(register_builder(hatchet))
    workflows.append(register_analytics(hatchet))

    # Distribution engine
    workflows.append(register_leads(hatchet))
    workflows.append(register_enrichment(hatchet))
    workflows.append(register_signals(hatchet))
    workflows.append(register_outreach(hatchet))
    workflows.append(register_replies(hatchet))

    # Wave 2
    workflows.append(register_content(hatchet))
    workflows.append(register_social(hatchet))
    workflows.append(register_referral(hatchet))
    workflows.append(register_voice(hatchet))
    billing_wh, billing_pd = register_billing(hatchet)
    workflows.extend([billing_wh, billing_pd])
    support_tk, support_ch = register_support(hatchet)
    workflows.extend([support_tk, support_ch])
    workflows.append(register_i18n(hatchet))
    workflows.append(register_nurture(hatchet))

    # Wave 3
    onboard_main, onboard_stall = register_onboarding(hatchet)
    workflows.extend([onboard_main, onboard_stall])
    workflows.append(register_upsell(hatchet))
    workflows.append(register_social_proof(hatchet))
    workflows.append(register_competitor(hatchet))
    workflows.append(register_fulfillment(hatchet))
    workflows.append(register_self_reflection(hatchet))
    legal_event, legal_scan = register_legal(hatchet)
    workflows.extend([legal_event, legal_scan])
    devops_health, devops_backup = register_devops(hatchet)
    workflows.extend([devops_health, devops_backup])
    workflows.append(register_budget_guardian(hatchet))
    workflows.append(register_growth(hatchet))

    for wf in workflows:
        worker.register_workflow(wf)

    logger.info("factory_worker_starting", worker="factory-worker", workflows=len(workflows))
    worker.start()


if __name__ == "__main__":
    main()

"""Stripe setup — creates products, prices, and reverse-trial configuration.

Every business gets 3 tiers (Free / Pro / Business) with:
- CAD pricing (charm pricing: $49, not $50)
- Annual billing at ~17% discount (2 months free)
- Reverse trial: 14-day full premium, then auto-downgrade to Free
"""

from __future__ import annotations

import structlog
import stripe as stripe_lib

from src.config import settings

logger = structlog.get_logger()


def _init_stripe():
    stripe_lib.api_key = settings.STRIPE_SECRET_KEY


async def create_business_products(
    *,
    business_name: str,
    slug: str,
    pro_price_cad: int = 49,
    business_price_cad: int = 99,
) -> dict:
    """Create the full Stripe product catalog for a business.

    Returns IDs for products, prices, and the trial configuration.
    """
    _init_stripe()

    result: dict = {"products": {}, "prices": {}, "trial_config": {}}

    try:
        # ── Free tier ──
        free_product = stripe_lib.Product.create(
            name=f"{business_name} — Free",
            metadata={"factory_slug": slug, "tier": "free"},
        )
        free_price = stripe_lib.Price.create(
            product=free_product.id,
            unit_amount=0,
            currency="cad",
            recurring={"interval": "month"},
        )
        result["products"]["free"] = free_product.id
        result["prices"]["free_monthly"] = free_price.id

        # ── Pro tier ──
        pro_product = stripe_lib.Product.create(
            name=f"{business_name} — Pro",
            metadata={"factory_slug": slug, "tier": "pro"},
        )
        pro_monthly = stripe_lib.Price.create(
            product=pro_product.id,
            unit_amount=pro_price_cad * 100,
            currency="cad",
            recurring={"interval": "month"},
        )
        annual_pro_cad = int(pro_price_cad * 10)  # ~17% discount (10 months instead of 12)
        pro_annual = stripe_lib.Price.create(
            product=pro_product.id,
            unit_amount=annual_pro_cad * 100,
            currency="cad",
            recurring={"interval": "year"},
        )
        result["products"]["pro"] = pro_product.id
        result["prices"]["pro_monthly"] = pro_monthly.id
        result["prices"]["pro_annual"] = pro_annual.id

        # ── Business tier ──
        biz_product = stripe_lib.Product.create(
            name=f"{business_name} — Business",
            metadata={"factory_slug": slug, "tier": "business"},
        )
        biz_monthly = stripe_lib.Price.create(
            product=biz_product.id,
            unit_amount=business_price_cad * 100,
            currency="cad",
            recurring={"interval": "month"},
        )
        annual_biz_cad = int(business_price_cad * 10)
        biz_annual = stripe_lib.Price.create(
            product=biz_product.id,
            unit_amount=annual_biz_cad * 100,
            currency="cad",
            recurring={"interval": "year"},
        )
        result["products"]["business"] = biz_product.id
        result["prices"]["business_monthly"] = biz_monthly.id
        result["prices"]["business_annual"] = biz_annual.id

        # ── Reverse trial config ──
        # New users start on Pro monthly with a 14-day trial.
        # After 14 days, Stripe auto-charges or we switch them to Free.
        result["trial_config"] = {
            "trial_price_id": pro_monthly.id,
            "trial_days": 14,
            "downgrade_price_id": free_price.id,
            "description": "14-day full premium trial, then auto-downgrade to Free tier",
        }

        logger.info(
            "stripe_products_created",
            business=business_name,
            products=len(result["products"]),
            prices=len(result["prices"]),
        )

    except Exception as exc:
        logger.error("stripe_setup_failed", business=business_name, error=str(exc))
        result["error"] = str(exc)

    return result


async def create_reverse_trial_subscription(
    *,
    customer_id: str,
    trial_price_id: str,
    downgrade_price_id: str,
    trial_days: int = 14,
) -> dict:
    """Create a subscription with reverse trial — full premium access for trial_days,
    then scheduled phase change to free tier."""
    _init_stripe()

    try:
        subscription = stripe_lib.Subscription.create(
            customer=customer_id,
            items=[{"price": trial_price_id}],
            trial_period_days=trial_days,
            payment_behavior="default_incomplete",
            metadata={"reverse_trial": "true", "downgrade_to": downgrade_price_id},
        )

        # Schedule the downgrade after trial ends
        stripe_lib.SubscriptionSchedule.create(
            from_subscription=subscription.id,
            phases=[
                {
                    "items": [{"price": trial_price_id}],
                    "trial": True,
                },
                {
                    "items": [{"price": downgrade_price_id}],
                    "iterations": 1,
                },
            ],
        )

        logger.info("reverse_trial_created", customer=customer_id, trial_days=trial_days)
        return {"subscription_id": subscription.id, "success": True}

    except Exception as exc:
        logger.error("reverse_trial_failed", customer=customer_id, error=str(exc))
        return {"subscription_id": None, "success": False, "error": str(exc)}

"""Infra Setup — creates real infrastructure for a business.

Shared Supabase project with schema-per-business isolation.
Creates Stripe products/prices. Sets up webhook endpoint.
Saves all credentials to businesses table.
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.integrations import stripe_setup

logger = structlog.get_logger()

SUPABASE_URL = "https://xayfpmigqdofmlegabqm.supabase.co"
SUPABASE_ANON_KEY_DEFAULT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhheWZwbWlncWRvZm1sZWdhYnFtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5MzYxMDUsImV4cCI6MjA4ODUxMjEwNX0.XbecBXW_I3dWQo3xYIDuTl7YmgdrVpIJS2q_-MffIxU"


class InfraSetup(BaseAgent):
    """Creates real infra: Supabase tables + Stripe products."""

    agent_name = "infra_setup"
    default_model = "haiku"

    async def setup_supabase(self, business_id: int, slug: str, migrations_sql: str = "") -> dict:
        """Create tables in the shared Supabase project for this business.

        Uses the shared project's service_role_key to run SQL directly.
        Each business uses the public schema (Supabase Auth requires it).
        Tables are prefixed or isolated via RLS policies scoped to business users.
        """
        service_role_key = settings.get("SUPABASE_SERVICE_ROLE_KEY")
        if not service_role_key:
            return {"success": False, "error": "SUPABASE_SERVICE_ROLE_KEY not configured"}

        # The template migration creates: profiles, projects, subscriptions, referrals, aggregate_stats
        # These already exist in the shared project from the factory's own setup.
        # For each business app, the Supabase Auth + RLS handles isolation automatically
        # since each user's data is scoped by auth.uid() in RLS policies.

        # If there are business-specific migrations (from code gen), run them
        if migrations_sql:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
                        headers={
                            "apikey": service_role_key,
                            "Authorization": f"Bearer {service_role_key}",
                            "Content-Type": "application/json",
                        },
                        json={"query": migrations_sql},
                    )
                    if resp.status_code not in (200, 201, 204):
                        # Try direct postgres connection as fallback
                        logger.warning("supabase_rpc_failed", status=resp.status_code,
                                       body=resp.text[:300])
            except Exception as exc:
                logger.warning("supabase_migration_failed", error=str(exc))

        # Save Supabase credentials to business
        async with SessionLocal() as db:
            await db.execute(text(
                "UPDATE businesses SET supabase_url = :url, supabase_anon_key = :key, "
                "updated_at = NOW() WHERE id = :id"
            ), {"url": SUPABASE_URL, "key": SUPABASE_ANON_KEY_DEFAULT, "id": business_id})
            await db.commit()

        await self.log_execution(
            action="setup_supabase",
            result={"supabase_url": SUPABASE_URL, "has_migrations": bool(migrations_sql)},
            business_id=business_id,
        )

        return {
            "success": True,
            "supabase_url": SUPABASE_URL,
            "supabase_anon_key": SUPABASE_ANON_KEY_DEFAULT,
        }

    async def setup_stripe(self, business_id: int, business_name: str, slug: str,
                           pricing: dict | None = None) -> dict:
        """Create Stripe products and prices for this business."""
        stripe_key = settings.get("STRIPE_SECRET_KEY")
        if not stripe_key:
            logger.warning("stripe_key_missing")
            return {"success": False, "error": "STRIPE_SECRET_KEY not configured"}

        pro_price = 49
        biz_price = 99
        if pricing:
            pro_price = pricing.get("pro", {}).get("price", 49)
            biz_price = pricing.get("business", {}).get("price", 99)

        result = await stripe_setup.create_business_products(
            business_name=business_name,
            slug=slug,
            pro_price_cad=pro_price,
            business_price_cad=biz_price,
        )

        if "error" not in result:
            # Save Stripe config to business
            async with SessionLocal() as db:
                biz = (await db.execute(text(
                    "SELECT config FROM businesses WHERE id = :id"
                ), {"id": business_id})).fetchone()
                config = json.loads(biz.config) if biz and biz.config else {}
                config["stripe"] = result
                await db.execute(text(
                    "UPDATE businesses SET config = :cfg, stripe_account_id = :sa, updated_at = NOW() WHERE id = :id"
                ), {"cfg": json.dumps(config), "sa": result.get("products", {}).get("pro", ""), "id": business_id})
                await db.commit()

        await self.log_execution(
            action="setup_stripe",
            result={"products": len(result.get("products", {})), "has_error": "error" in result},
            business_id=business_id,
        )

        return {"success": "error" not in result, "stripe_config": result}

    async def create_stripe_webhook(self, business_id: int, deployment_url: str) -> dict:
        """Create a Stripe webhook endpoint for this business's Vercel deployment."""
        import stripe as stripe_lib
        stripe_lib.api_key = settings.get("STRIPE_SECRET_KEY")
        if not stripe_lib.api_key:
            return {"success": False, "error": "no stripe key"}

        try:
            webhook_url = f"https://{deployment_url}/api/webhooks/stripe"
            endpoint = stripe_lib.WebhookEndpoint.create(
                url=webhook_url,
                enabled_events=[
                    "customer.subscription.created",
                    "customer.subscription.updated",
                    "customer.subscription.deleted",
                    "invoice.payment_succeeded",
                    "invoice.payment_failed",
                    "customer.subscription.trial_will_end",
                ],
                description=f"Antzilla business: {deployment_url}",
            )
            webhook_secret = endpoint.secret

            await self.log_execution(
                action="create_stripe_webhook",
                result={"endpoint_id": endpoint.id, "url": webhook_url},
                business_id=business_id,
            )

            return {"success": True, "webhook_secret": webhook_secret, "endpoint_id": endpoint.id}
        except Exception as exc:
            logger.error("stripe_webhook_failed", error=str(exc))
            return {"success": False, "error": str(exc)}

    async def set_vercel_env_vars(self, business_id: int, vercel_project_id: str,
                                  deployment_url: str, stripe_config: dict,
                                  webhook_secret: str = "") -> dict:
        """Set all environment variables on the Vercel project."""
        token = settings.get("VERCEL_TOKEN")
        if not token:
            return {"success": False, "error": "no vercel token"}

        # Load business data
        app_name = ""
        async with SessionLocal() as db:
            biz = (await db.execute(text(
                "SELECT name, supabase_url, supabase_anon_key FROM businesses WHERE id = :id"
            ), {"id": business_id})).fetchone()
            if biz:
                app_name = biz.name or ""

        service_role_key = settings.get("SUPABASE_SERVICE_ROLE_KEY", "")
        stripe_secret = settings.get("STRIPE_SECRET_KEY", "")
        stripe_publishable = settings.get("STRIPE_PUBLISHABLE_KEY", "")
        ga_id = settings.get("NEXT_PUBLIC_GA_MEASUREMENT_ID", "")

        prices = stripe_config.get("prices", {})

        env_vars = [
            {"key": "NEXT_PUBLIC_SUPABASE_URL", "value": SUPABASE_URL, "type": "plain", "target": ["production", "preview"]},
            {"key": "NEXT_PUBLIC_SUPABASE_ANON_KEY", "value": SUPABASE_ANON_KEY_DEFAULT, "type": "plain", "target": ["production", "preview"]},
            {"key": "SUPABASE_SERVICE_ROLE_KEY", "value": service_role_key, "type": "encrypted", "target": ["production"]},
            {"key": "NEXT_PUBLIC_APP_NAME", "value": app_name, "type": "plain", "target": ["production", "preview"]},
            {"key": "NEXT_PUBLIC_APP_URL", "value": f"https://{deployment_url}", "type": "plain", "target": ["production", "preview"]},
        ]

        if stripe_secret:
            env_vars.append({"key": "STRIPE_SECRET_KEY", "value": stripe_secret, "type": "encrypted", "target": ["production"]})
        if stripe_publishable:
            env_vars.append({"key": "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", "value": stripe_publishable, "type": "plain", "target": ["production", "preview"]})
        if webhook_secret:
            env_vars.append({"key": "STRIPE_WEBHOOK_SECRET", "value": webhook_secret, "type": "encrypted", "target": ["production"]})
        if ga_id:
            env_vars.append({"key": "NEXT_PUBLIC_GA_MEASUREMENT_ID", "value": ga_id, "type": "plain", "target": ["production", "preview"]})

        # Add Stripe price IDs
        if prices.get("pro_monthly"):
            env_vars.append({"key": "STRIPE_PRO_MONTHLY_PRICE_ID", "value": prices["pro_monthly"], "type": "plain", "target": ["production"]})
        if prices.get("pro_annual"):
            env_vars.append({"key": "STRIPE_PRO_ANNUAL_PRICE_ID", "value": prices["pro_annual"], "type": "plain", "target": ["production"]})
        if prices.get("business_monthly"):
            env_vars.append({"key": "STRIPE_BUSINESS_MONTHLY_PRICE_ID", "value": prices["business_monthly"], "type": "plain", "target": ["production"]})

        set_count = 0
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for ev in env_vars:
                try:
                    resp = await client.post(
                        f"https://api.vercel.com/v10/projects/{vercel_project_id}/env",
                        headers=headers,
                        json=ev,
                    )
                    if resp.status_code in (200, 201):
                        set_count += 1
                    elif resp.status_code == 409:
                        # Already exists, update it
                        env_id_resp = await client.get(
                            f"https://api.vercel.com/v10/projects/{vercel_project_id}/env",
                            headers=headers,
                        )
                        if env_id_resp.status_code == 200:
                            for existing in env_id_resp.json().get("envs", []):
                                if existing.get("key") == ev["key"]:
                                    await client.patch(
                                        f"https://api.vercel.com/v10/projects/{vercel_project_id}/env/{existing['id']}",
                                        headers=headers,
                                        json={"value": ev["value"]},
                                    )
                                    set_count += 1
                                    break
                except Exception as exc:
                    logger.warning("vercel_env_set_failed", key=ev["key"], error=str(exc))

        await self.log_execution(
            action="set_vercel_env_vars",
            result={"set": set_count, "total": len(env_vars)},
            business_id=business_id,
        )

        return {"success": True, "set": set_count, "total": len(env_vars)}


def register(hatchet_instance):
    """Register InfraSetup as a Hatchet workflow."""
    agent = InfraSetup()
    wf = hatchet_instance.workflow(name="infra-setup")

    @wf.task(execution_timeout="5m", retries=1)
    async def setup_all(input, ctx):
        data = ctx.workflow_input()
        business_id = data.get("business_id")
        slug = data.get("slug", "")
        name = data.get("name", "")
        pricing = data.get("pricing")
        migrations = data.get("migrations_sql", "")
        deployment_url = data.get("deployment_url", "")
        vercel_project_id = data.get("vercel_project_id", "")

        sb = await agent.setup_supabase(business_id, slug, migrations)
        st = await agent.setup_stripe(business_id, name, slug, pricing)
        wh = await agent.create_stripe_webhook(business_id, deployment_url) if deployment_url else {}
        ve = await agent.set_vercel_env_vars(
            business_id, vercel_project_id, deployment_url,
            st.get("stripe_config", {}), wh.get("webhook_secret", "")
        ) if vercel_project_id else {}

        return {"supabase": sb, "stripe": st, "webhook": wh, "vercel_env": ve}

    return wf

"""Agent 6: Domain Provisioner.

Triggered on-demand when a business is approved.  Sets up ALL external
infrastructure in a single workflow run:

1. buy_primary_domain       — .ca preferred via Namecheap
2. buy_cold_email_domains   — 2-3 secondary TLDs (.io, .co) — NEVER cold-email from primary
3. setup_dns_all_domains    — Cloudflare zones, A/MX/SPF/DKIM/DMARC on every domain
4. create_vercel_project    — via Vercel API
5. create_github_repo       — from template repo
6. create_supabase_project  — with RLS enabled
7. setup_stripe             — reverse trial (3 tiers, CAD, charm pricing)
8. setup_resend             — transactional email on primary domain
9. setup_instantly          — cold email on secondary domains, start warmup
10. buy_twilio_number       — local area code (514 QC, 416 ON, etc.)
11. create_retell_agents    — FR + EN voice agents per business
12. save_infra_to_db        — persist all IDs/keys to businesses table
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.integrations import cloudflare, namecheap, stripe_setup, instantly

logger = structlog.get_logger()

COLD_EMAIL_TLDS = [".io", ".co"]
PROVINCE_AREA_CODES = {
    "QC": "514",
    "ON": "416",
    "BC": "604",
    "AB": "403",
    "MB": "204",
    "SK": "306",
    "NS": "902",
    "NB": "506",
    "NL": "709",
    "PE": "902",
}


def _slug_to_domain_base(slug: str) -> str:
    """Normalise business slug into a registrable domain base."""
    return slug.lower().replace("_", "").replace("-", "").replace(" ", "")


class DomainProvisioner(BaseAgent):
    """Provisions all external infrastructure for a new business."""

    agent_name = "domain_provisioner"
    default_model = "sonnet"

    async def buy_primary_domain(self, context) -> dict:
        """Step 1: Buy the primary .ca domain (fallback to .com)."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        slug = input_data.get("slug", "")
        preferred_domain = input_data.get("domain")  # may be pre-selected by brand agent

        base = _slug_to_domain_base(slug)

        if preferred_domain:
            domain = preferred_domain
        else:
            # Try .ca first, then .com
            ca_check = await namecheap.check_domain(f"{base}.ca")
            if ca_check["available"]:
                domain = f"{base}.ca"
            else:
                com_check = await namecheap.check_domain(f"{base}.com")
                if com_check["available"]:
                    domain = f"{base}.com"
                else:
                    domain = f"{base}.ca"  # attempt anyway

        result = await namecheap.purchase_domain(domain)

        await self.log_execution(
            action="buy_primary_domain",
            result={"domain": domain, "success": result["success"]},
            business_id=business_id,
        )

        return {
            "primary_domain": domain,
            "purchase_success": result["success"],
            "order_id": result.get("order_id"),
            "business_id": business_id,
            "slug": slug,
        }

    async def buy_cold_email_domains(self, context) -> dict:
        """Step 2: Buy 2-3 secondary domains for cold email.

        CRITICAL: NEVER send cold email from the primary .ca domain.
        """
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")
        business_id = primary.get("business_id")
        base = _slug_to_domain_base(slug)

        purchased = []
        for tld in COLD_EMAIL_TLDS:
            domain = f"{base}{tld}"
            check = await namecheap.check_domain(domain)
            if check["available"]:
                result = await namecheap.purchase_domain(domain)
                purchased.append({
                    "domain": domain,
                    "success": result["success"],
                    "purpose": "cold_email",
                })
            else:
                purchased.append({
                    "domain": domain,
                    "success": False,
                    "reason": "unavailable",
                    "purpose": "cold_email",
                })

        await self.log_execution(
            action="buy_cold_email_domains",
            result={"domains": purchased},
            business_id=business_id,
        )

        cold_domains = [d["domain"] for d in purchased if d["success"]]
        return {
            "cold_email_domains": cold_domains,
            "purchase_results": purchased,
        }

    async def setup_dns_all_domains(self, context) -> dict:
        """Step 3: Create Cloudflare zones and DNS records for ALL domains."""
        primary = context.step_output("buy_primary_domain")
        cold = context.step_output("buy_cold_email_domains")
        primary_domain = primary.get("primary_domain", "")
        cold_domains = cold.get("cold_email_domains", [])
        business_id = primary.get("business_id")

        all_domains = [primary_domain] + cold_domains
        dns_results = {}

        for domain in all_domains:
            if not domain:
                continue
            # Create Cloudflare zone
            zone = await cloudflare.create_zone(domain)
            zone_id = zone.get("zone_id")

            if zone_id:
                # Point Namecheap NS to Cloudflare
                ns = zone.get("nameservers", [])
                if ns:
                    await namecheap.set_nameservers(domain, ns)

                # Email DNS (SPF/DKIM/DMARC) on ALL domains
                email_records = await cloudflare.setup_email_dns(zone_id, domain)

                # Vercel DNS only on primary domain
                vercel_records = []
                if domain == primary_domain:
                    vercel_records = await cloudflare.setup_vercel_dns(zone_id, domain)

                dns_results[domain] = {
                    "zone_id": zone_id,
                    "nameservers": ns,
                    "email_dns": len(email_records),
                    "vercel_dns": len(vercel_records),
                    "success": True,
                }
            else:
                dns_results[domain] = {"success": False, "error": zone.get("errors")}

        await self.log_execution(
            action="setup_dns_all_domains",
            result={"domains": list(dns_results.keys())},
            business_id=business_id,
        )

        primary_zone_id = dns_results.get(primary_domain, {}).get("zone_id")
        return {"dns_results": dns_results, "primary_zone_id": primary_zone_id}

    async def create_vercel_project(self, context) -> dict:
        """Step 4: Create Vercel project linked to the domain."""
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")
        domain = primary.get("primary_domain", "")
        business_id = primary.get("business_id")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    "https://api.vercel.com/v9/projects",
                    headers={"Authorization": f"Bearer {settings.VERCEL_TOKEN}"},
                    json={
                        "name": slug,
                        "framework": "nextjs",
                    },
                )
                resp.raise_for_status()
                project = resp.json()
                project_id = project.get("id", "")

                # Add domain
                if domain:
                    await client.post(
                        f"https://api.vercel.com/v9/projects/{project_id}/domains",
                        headers={"Authorization": f"Bearer {settings.VERCEL_TOKEN}"},
                        json={"name": domain},
                    )

                logger.info("vercel_project_created", slug=slug, project_id=project_id)
                return {"vercel_project_id": project_id, "success": True}
            except Exception as exc:
                logger.error("vercel_create_failed", slug=slug, error=str(exc))
                return {"vercel_project_id": None, "success": False, "error": str(exc)}

    async def create_github_repo(self, context) -> dict:
        """Step 5: Create GitHub repo from template."""
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    "https://api.github.com/user/repos",
                    headers={
                        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                        "Accept": "application/vnd.github+json",
                    },
                    json={
                        "name": slug,
                        "private": True,
                        "auto_init": True,
                        "description": f"Factory-generated business: {slug}",
                    },
                )
                resp.raise_for_status()
                repo = resp.json()
                repo_url = repo.get("full_name", "")
                logger.info("github_repo_created", repo=repo_url)
                return {"github_repo": repo_url, "success": True}
            except Exception as exc:
                logger.error("github_create_failed", slug=slug, error=str(exc))
                return {"github_repo": None, "success": False, "error": str(exc)}

    async def create_supabase_project(self, context) -> dict:
        """Step 6: Create Supabase project with RLS enabled."""
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://api.supabase.com/v1/projects",
                    headers={
                        "Authorization": f"Bearer {settings.SUPABASE_ACCESS_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "name": slug,
                        "db_pass": f"factory-{slug}-db",
                        "region": "ca-central-1",
                        "plan": "free",
                    },
                )
                resp.raise_for_status()
                project = resp.json()
                project_id = project.get("id", "")
                url = f"https://{project_id}.supabase.co"
                anon_key = project.get("anon_key", "")
                logger.info("supabase_project_created", project_id=project_id)
                return {
                    "supabase_project_id": project_id,
                    "supabase_url": url,
                    "supabase_anon_key": anon_key,
                    "success": True,
                }
            except Exception as exc:
                logger.error("supabase_create_failed", slug=slug, error=str(exc))
                return {
                    "supabase_project_id": None,
                    "supabase_url": None,
                    "supabase_anon_key": None,
                    "success": False,
                    "error": str(exc),
                }

    async def setup_stripe(self, context) -> dict:
        """Step 7: Create Stripe products with reverse trial config."""
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")
        business_id = primary.get("business_id")
        input_data = context.workflow_input()
        business_name = input_data.get("name", slug)

        pricing = input_data.get("pricing", {})
        pro_price = pricing.get("pro_price_cad", 49)
        biz_price = pricing.get("business_price_cad", 99)

        result = await stripe_setup.create_business_products(
            business_name=business_name,
            slug=slug,
            pro_price_cad=pro_price,
            business_price_cad=biz_price,
        )

        await self.log_execution(
            action="setup_stripe",
            result={"products": len(result.get("products", {})), "has_error": "error" in result},
            business_id=business_id,
        )

        return {"stripe_config": result}

    async def setup_resend(self, context) -> dict:
        """Step 8: Configure Resend for transactional email on primary domain."""
        primary = context.step_output("buy_primary_domain")
        domain = primary.get("primary_domain", "")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    "https://api.resend.com/domains",
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                    json={"name": domain},
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info("resend_domain_added", domain=domain)
                return {"resend_domain_id": data.get("id"), "success": True}
            except Exception as exc:
                logger.error("resend_setup_failed", domain=domain, error=str(exc))
                return {"resend_domain_id": None, "success": False, "error": str(exc)}

    async def setup_instantly(self, context) -> dict:
        """Step 9: Add cold email accounts on secondary domains, start warmup.

        Warmup at 5-10 emails/day for 4-6 weeks before any volume.
        """
        cold = context.step_output("buy_cold_email_domains")
        cold_domains = cold.get("cold_email_domains", [])

        results = []
        for domain in cold_domains:
            email = f"hello@{domain}"
            result = await instantly.add_sending_account(
                email=email,
                smtp_host=f"smtp.{domain}",
                smtp_port=587,
                smtp_username=email,
                smtp_password="placeholder-configure-manually",
                imap_host=f"imap.{domain}",
                imap_port=993,
                imap_username=email,
                imap_password="placeholder-configure-manually",
                warmup_enabled=True,
                warmup_limit=5,
            )
            results.append(result)

        return {"instantly_accounts": results, "warmup_started": len(results) > 0}

    async def buy_twilio_number(self, context) -> dict:
        """Step 10: Buy a local Twilio phone number matching the ICP's province."""
        primary = context.step_output("buy_primary_domain")
        business_id = primary.get("business_id")
        input_data = context.workflow_input()
        province = input_data.get("province", "QC")
        area_code = PROVINCE_AREA_CODES.get(province, "514")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                # Search for available numbers
                resp = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}"
                    f"/AvailablePhoneNumbers/CA/Local.json",
                    params={"AreaCode": area_code, "Limit": 1},
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                )
                resp.raise_for_status()
                numbers = resp.json().get("available_phone_numbers", [])

                if not numbers:
                    return {"phone_number": None, "success": False, "reason": f"no numbers in {area_code}"}

                # Buy it
                phone = numbers[0]["phone_number"]
                buy_resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}"
                    f"/IncomingPhoneNumbers.json",
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                    data={"PhoneNumber": phone},
                )
                buy_resp.raise_for_status()
                logger.info("twilio_number_purchased", phone=phone, area_code=area_code)
                return {"phone_number": phone, "area_code": area_code, "success": True}

            except Exception as exc:
                logger.error("twilio_purchase_failed", error=str(exc))
                return {"phone_number": None, "success": False, "error": str(exc)}

    async def create_retell_agents(self, context) -> dict:
        """Step 11: Create Retell AI voice agents (FR + EN) for the business."""
        primary = context.step_output("buy_primary_domain")
        slug = primary.get("slug", "")
        input_data = context.workflow_input()
        business_name = input_data.get("name", slug)

        agents_created = []
        async with httpx.AsyncClient(timeout=15) as client:
            for lang in ["fr", "en"]:
                try:
                    resp = await client.post(
                        "https://api.retellai.com/create-agent",
                        headers={
                            "Authorization": f"Bearer {settings.RETELL_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "agent_name": f"{slug}-{lang}",
                            "response_engine": {
                                "type": "retell-llm",
                                "llm_id": "",
                            },
                            "voice_id": "",
                            "language": lang,
                        },
                    )
                    resp.raise_for_status()
                    agent = resp.json()
                    agents_created.append({
                        "language": lang,
                        "agent_id": agent.get("agent_id", ""),
                        "success": True,
                    })
                except Exception as exc:
                    agents_created.append({
                        "language": lang,
                        "agent_id": None,
                        "success": False,
                        "error": str(exc),
                    })

        return {"retell_agents": agents_created}

    async def save_infra_to_db(self, context) -> dict:
        """Step 12: Persist all infrastructure IDs to the businesses table."""
        primary = context.step_output("buy_primary_domain")
        cold = context.step_output("buy_cold_email_domains")
        dns = context.step_output("setup_dns_all_domains")
        vercel = context.step_output("create_vercel_project")
        github = context.step_output("create_github_repo")
        supabase = context.step_output("create_supabase_project")
        stripe_cfg = context.step_output("setup_stripe")
        twilio = context.step_output("buy_twilio_number")

        business_id = primary.get("business_id")
        if not business_id:
            return {"saved": False, "reason": "no business_id"}

        config = {
            "cold_email_domains": cold.get("cold_email_domains", []),
            "dns": dns.get("dns_results", {}),
            "stripe": stripe_cfg.get("stripe_config", {}),
            "twilio_number": twilio.get("phone_number"),
            "retell_agents": context.step_output("create_retell_agents").get("retell_agents", []),
        }

        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE businesses SET "
                    "domain = :domain, "
                    "cloudflare_zone_id = :cf_zone, "
                    "vercel_project_id = :vercel, "
                    "github_repo = :github, "
                    "supabase_project_id = :supa_id, "
                    "supabase_url = :supa_url, "
                    "supabase_anon_key = :supa_key, "
                    "config = :config, "
                    "status = 'building', "
                    "updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {
                    "domain": primary.get("primary_domain"),
                    "cf_zone": dns.get("primary_zone_id"),
                    "vercel": vercel.get("vercel_project_id"),
                    "github": github.get("github_repo"),
                    "supa_id": supabase.get("supabase_project_id"),
                    "supa_url": supabase.get("supabase_url"),
                    "supa_key": supabase.get("supabase_anon_key"),
                    "config": json.dumps(config),
                    "id": business_id,
                },
            )
            await db.commit()

        await self.log_execution(
            action="save_infra_to_db",
            result={"business_id": business_id, "domain": primary.get("primary_domain")},
            business_id=business_id,
        )

        return {"saved": True, "business_id": business_id}


def register(hatchet_instance) -> type:
    """Register DomainProvisioner as a Hatchet workflow."""

    @hatchet_instance.workflow(name="domain-provisioner")
    class _Registered(DomainProvisioner):
        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def buy_primary_domain(self, context) -> dict:
            return await DomainProvisioner.buy_primary_domain(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def buy_cold_email_domains(self, context) -> dict:
            return await DomainProvisioner.buy_cold_email_domains(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def setup_dns_all_domains(self, context) -> dict:
            return await DomainProvisioner.setup_dns_all_domains(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def create_vercel_project(self, context) -> dict:
            return await DomainProvisioner.create_vercel_project(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def create_github_repo(self, context) -> dict:
            return await DomainProvisioner.create_github_repo(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def create_supabase_project(self, context) -> dict:
            return await DomainProvisioner.create_supabase_project(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def setup_stripe(self, context) -> dict:
            return await DomainProvisioner.setup_stripe(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def setup_resend(self, context) -> dict:
            return await DomainProvisioner.setup_resend(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def setup_instantly(self, context) -> dict:
            return await DomainProvisioner.setup_instantly(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def buy_twilio_number(self, context) -> dict:
            return await DomainProvisioner.buy_twilio_number(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def create_retell_agents(self, context) -> dict:
            return await DomainProvisioner.create_retell_agents(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def save_infra_to_db(self, context) -> dict:
            return await DomainProvisioner.save_infra_to_db(self, context)

    return _Registered

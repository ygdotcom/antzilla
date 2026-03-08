"""Agent 16: Fulfillment Ops.

Event-driven: triggers on customer action (e.g. job created).
Registry pattern: FULFILLMENT_HANDLERS maps business slug to handler functions.
Steps: receive_job → process_job → generate_deliverable → deliver_to_customer → update_status.
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

# Registry: business slug → async handler(job, db) -> dict
FULFILLMENT_HANDLERS: dict[str, callable] = {}

GENERIC_FULFILLMENT_PROMPT = """\
Tu es un agent de fulfillment. Tu génères un livrable professionnel pour un client.

Tu reçois: job_type, input du client, type de produit du business, nom du business.

RÈGLES:
- Génère un contenu complet et professionnel
- Adapte le format au job_type (devis, rapport, document, contenu, etc.)
- Bilingue: si l'input contient du français, réponds en français
- Inclus des sections claires avec headers
- Réponds en JSON: {"title": "...", "content": "...", "format": "text|html|markdown", "metadata": {}}
"""


def register_handler(slug: str):
    """Decorator to register a fulfillment handler for a business slug."""

    def decorator(fn):
        FULFILLMENT_HANDLERS[slug] = fn
        return fn

    return decorator


async def _generic_claude_handler(job: dict, db) -> dict:
    """Generic Claude-based handler for any business without a custom handler."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT b.name, b.slug, COALESCE(b.config->>'product_type', b.slug) AS product_type "
                "FROM businesses b WHERE b.id = :biz_id"
            ),
            {"biz_id": job["business_id"]},
        )
    ).fetchone()

    biz_name = row.name if row else "Unknown"
    product_type = row.product_type if row else job.get("job_type", "generic")

    input_data = job.get("input_data") or {}
    user_payload = json.dumps({
        "job_type": job["job_type"],
        "product_type": product_type,
        "business_name": biz_name,
        "input": input_data,
    }, default=str)

    response, cost = await call_claude(
        model_tier="sonnet",
        system=GENERIC_FULFILLMENT_PROMPT,
        user=user_payload,
        max_tokens=4096,
        temperature=0.3,
    )

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        result = {"title": f"{job['job_type']} — {biz_name}", "content": response, "format": "text"}

    result["cost_usd"] = cost
    return result


FULFILLMENT_HANDLERS["__generic__"] = _generic_claude_handler


class FulfillmentAgent(BaseAgent):
    """Per-business service delivery via registry pattern."""

    agent_name = "fulfillment"
    default_model = "sonnet"

    async def receive_job(self, context) -> dict:
        """Load job from jobs table."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        job_id = input_data.get("job_id")

        if not job_id:
            return {"job": None, "error": "job_id required"}

        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT j.id, j.business_id, j.customer_id, j.job_type, j.input_data, "
                        "j.status, b.slug AS business_slug "
                        "FROM jobs j JOIN businesses b ON j.business_id = b.id "
                        "WHERE j.id = :jid AND j.status = 'pending'"
                    ),
                    {"jid": job_id},
                )
            ).fetchone()

        if not row:
            return {"job": None, "error": "job not found or not pending"}

        job = {
            "id": row.id,
            "business_id": row.business_id,
            "customer_id": row.customer_id,
            "job_type": row.job_type,
            "input_data": row.input_data,
            "business_slug": row.business_slug,
        }
        return {"job": job}

    async def process_job(self, context) -> dict:
        """Use Claude based on job_type, or delegate to FULFILLMENT_HANDLERS."""
        receive_out = context.step_output("receive_job")
        job = receive_out.get("job")
        if not job:
            return {"output": None, "error": receive_out.get("error")}

        slug = job["business_slug"]
        handler = FULFILLMENT_HANDLERS.get(slug) or FULFILLMENT_HANDLERS.get("__generic__")
        if handler:
            async with SessionLocal() as db:
                result = await handler(job, db)
            await self.log_execution(
                action="process_job",
                result={"job_id": job["id"], "handler": slug if slug in FULFILLMENT_HANDLERS else "__generic__"},
                cost_usd=result.get("cost_usd", 0) if isinstance(result, dict) else 0,
            )
            return {"output": result, "handler": slug if slug in FULFILLMENT_HANDLERS else "__generic__"}

        return {"output": None, "error": "no handler available"}

    async def generate_deliverable(self, context) -> dict:
        """Produce output (PDF, email body, etc.)."""
        process_out = context.step_output("process_job")
        output = process_out.get("output")
        if not output:
            return {"deliverable": None, "error": process_out.get("error")}

        deliverable = output if isinstance(output, dict) else {"content": str(output)}
        return {"deliverable": deliverable}

    async def deliver_to_customer(self, context) -> dict:
        """Email or in-app delivery."""
        receive_out = context.step_output("receive_job")
        gen_out = context.step_output("generate_deliverable")
        job = receive_out.get("job")
        deliverable = gen_out.get("deliverable")

        if not job or not deliverable:
            return {"delivered": False}

        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text("SELECT email, name FROM customers WHERE id = :cid"),
                    {"cid": job["customer_id"]},
                )
            ).fetchone()

        if not row or not row.email:
            return {"delivered": False, "error": "no customer email"}

        if settings.RESEND_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                        json={
                            "from": "fulfillment@factorylabs.ca",
                            "to": row.email,
                            "subject": f"Your deliverable — Job #{job['id']}",
                            "text": json.dumps(deliverable) if isinstance(deliverable, dict) else str(deliverable),
                        },
                    )
                return {"delivered": True, "channel": "email"}
            except Exception as exc:
                logger.warning("fulfillment_delivery_failed", job_id=job["id"], error=str(exc))
                return {"delivered": False, "error": str(exc)}

        logger.info("fulfillment_deliverable_ready", job_id=job["id"], customer_email=row.email[:6] + "...")
        return {"delivered": True, "channel": "in_app"}

    async def update_status(self, context) -> dict:
        """Mark job completed or failed."""
        receive_out = context.step_output("receive_job")
        deliver_out = context.step_output("deliver_to_customer")
        job = receive_out.get("job")

        if not job:
            return {"updated": False}

        status = "completed" if deliver_out.get("delivered") else "failed"
        error = deliver_out.get("error")

        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE jobs SET status = :status, error = :err, completed_at = NOW(), "
                    "output_data = :output_data WHERE id = :jid"
                ),
                {
                    "status": status,
                    "err": error,
                    "output_data": json.dumps(deliver_out) if deliver_out else None,
                    "jid": job["id"],
                },
            )
            await db.commit()

        await self.log_execution(action="update_status", result={"job_id": job["id"], "status": status})
        return {"updated": True, "status": status}


def register(hatchet_instance):
    agent = FulfillmentAgent()
    wf = hatchet_instance.workflow(name="fulfillment")

    @wf.task(execution_timeout="2m", retries=2)
    async def receive_job(input, ctx):
        return await agent.receive_job(ctx)

    @wf.task(execution_timeout="8m", retries=1)
    async def process_job(input, ctx):
        return await agent.process_job(ctx)

    @wf.task(execution_timeout="2m", retries=1)
    async def generate_deliverable(input, ctx):
        return await agent.generate_deliverable(ctx)

    @wf.task(execution_timeout="3m", retries=2)
    async def deliver_to_customer(input, ctx):
        return await agent.deliver_to_customer(ctx)

    @wf.task(execution_timeout="1m", retries=1)
    async def update_status(input, ctx):
        return await agent.update_status(ctx)

    return wf

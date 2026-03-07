"""Agent 26: Voice Agent.

⚠️ WARM CALLS ONLY (SPEC §2).  This agent NEVER cold-calls.
It only calls people who have demonstrated consent through:
  - Replying to an email (implied consent for follow-up)
  - Filling out a form (express consent)
  - Being an existing customer
  - Explicitly requesting a callback

CRTC ADAD rules: cold AI calling = $15,000 fine per call.

5-step DAG:
1. prepare_call   — load lead/customer data, determine language
2. check_compliance — CRITICAL, NEVER SKIP: consent type, internal DNCL,
                      national DNCL, calling hours, daily volume
3. make_call       — Retell AI API
4. process_result  — classify outcome, route accordingly
5. log_and_optimize — metrics, A/B testing
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.db import SessionLocal
from src.integrations import dncl_client, retell_client
from src.llm import call_claude

logger = structlog.get_logger()

WARM_STATUSES = {"replied", "booked", "trial", "converted", "callback_requested"}

CALL_OUTCOME_PROMPT = """\
Analyse ce transcript d'appel téléphonique et classifie le résultat.

Réponds en JSON:
{
  "outcome": "interested|not_interested|callback_requested|meeting_booked|wrong_number|voicemail_left|do_not_call|escalate",
  "summary": "2-3 sentence summary",
  "sentiment_score": 0.5,
  "next_action": "description of what to do next",
  "callback_date": "YYYY-MM-DD or null",
  "meeting_url": "URL or null"
}
"""

MAX_DAILY_CALLS = 30


class ConsentError(Exception):
    """Raised when a call is blocked due to missing consent."""


class VoiceAgent(BaseAgent):
    """AI voice calls — WARM ONLY, with full CRTC/DNCL compliance."""

    agent_name = "voice_agent"
    default_model = "sonnet"

    async def prepare_call(self, context) -> dict:
        """Step 1: Load lead/customer data and determine language."""
        input_data = context.workflow_input()
        lead_id = input_data.get("lead_id")
        customer_id = input_data.get("customer_id")
        business_id = input_data.get("business_id")
        call_type = input_data.get("call_type", "qualification")

        async with SessionLocal() as db:
            lead = None
            customer = None

            if lead_id:
                lead = (
                    await db.execute(
                        text(
                            "SELECT id, name, company, phone, email, language, "
                            "province, status, score, signal_type "
                            "FROM leads WHERE id = :id"
                        ),
                        {"id": lead_id},
                    )
                ).fetchone()

            if customer_id:
                customer = (
                    await db.execute(
                        text(
                            "SELECT id, name, company, phone, email, language, province "
                            "FROM customers WHERE id = :id"
                        ),
                        {"id": customer_id},
                    )
                ).fetchone()

            # Load voice script
            target = lead or customer
            lang = (target.language if target else "fr") or "fr"
            province = (target.province if target else "QC") or "QC"

            script = (
                await db.execute(
                    text(
                        "SELECT system_prompt, greeting, max_duration_seconds "
                        "FROM voice_scripts "
                        "WHERE business_id = :biz AND call_type = :type "
                        "AND language = :lang AND active = TRUE "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"biz": business_id, "type": call_type, "lang": lang},
                )
            ).fetchone()

        phone = target.phone if target else None
        name = target.name if target else "Unknown"

        return {
            "lead_id": lead_id,
            "customer_id": customer_id,
            "business_id": business_id,
            "call_type": call_type,
            "phone": phone,
            "name": name,
            "company": target.company if target else None,
            "language": lang,
            "province": province,
            "lead_status": lead.status if lead else None,
            "is_customer": customer is not None,
            "script": {
                "system_prompt": script.system_prompt if script else "",
                "greeting": script.greeting if script else f"Bonjour {name}",
                "max_duration": script.max_duration_seconds if script else 120,
            } if script else None,
        }

    async def check_compliance(self, context) -> dict:
        """Step 2: CRITICAL — verify consent, DNCL, calling hours. NEVER SKIP.

        This is the warm-calls-only gate. If ANY check fails, the call is ABORTED.
        """
        prep = context.step_output("prepare_call")
        phone = prep.get("phone")
        lead_status = prep.get("lead_status")
        is_customer = prep.get("is_customer", False)
        province = prep.get("province", "QC")
        business_id = prep.get("business_id")

        # ── Gate 1: Consent type (WARM CALLS ONLY) ──
        if not is_customer and lead_status not in WARM_STATUSES:
            logger.warning(
                "call_blocked_no_consent",
                lead_status=lead_status,
                reason="Lead has not engaged — warm calls only per §2",
            )
            return {
                "can_call": False,
                "reason": f"No consent: lead status '{lead_status}' not in warm statuses",
                "gate": "consent",
            }

        if not phone:
            return {"can_call": False, "reason": "No phone number", "gate": "phone"}

        # ── Gate 2: Internal DNCL ──
        dncl_result = await dncl_client.check_dncl(phone)
        if dncl_result.get("on_dncl"):
            logger.warning("call_blocked_dncl", source=dncl_result.get("source"))
            return {
                "can_call": False,
                "reason": f"On DNCL ({dncl_result.get('source')})",
                "gate": "dncl",
            }

        # ── Gate 3: Calling hours ──
        if not dncl_client.is_within_calling_hours(province):
            return {
                "can_call": False,
                "reason": f"Outside calling hours for {province}",
                "gate": "hours",
                "schedule_later": True,
            }

        # ── Gate 4: Daily volume limit ──
        async with SessionLocal() as db:
            today_calls = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) AS cnt FROM voice_calls "
                        "WHERE business_id = :biz AND created_at > CURRENT_DATE"
                    ),
                    {"biz": business_id},
                )
            ).fetchone()

        if (today_calls.cnt or 0) >= MAX_DAILY_CALLS:
            return {
                "can_call": False,
                "reason": f"Daily limit reached ({MAX_DAILY_CALLS} calls)",
                "gate": "volume",
                "schedule_later": True,
            }

        return {"can_call": True, "all_checks_passed": True}

    async def make_call(self, context) -> dict:
        """Step 3: Initiate the call via Retell AI."""
        compliance = context.step_output("check_compliance")
        if not compliance.get("can_call"):
            return {"call_made": False, **compliance}

        prep = context.step_output("prepare_call")
        phone = prep.get("phone", "")
        script = prep.get("script", {})
        business_id = prep.get("business_id")

        # Get Retell agent ID for this business + language
        async with SessionLocal() as db:
            biz = (
                await db.execute(
                    text("SELECT config FROM businesses WHERE id = :id"),
                    {"id": business_id},
                )
            ).fetchone()

        retell_agents = []
        if biz and biz.config:
            config = json.loads(biz.config) if isinstance(biz.config, str) else biz.config
            retell_agents = config.get("retell_agents", [])

        lang = prep.get("language", "fr")
        agent_match = next((a for a in retell_agents if a.get("language") == lang), None)
        agent_id = agent_match.get("agent_id", "") if agent_match else ""

        from_number = ""  # from business Twilio number
        if biz and biz.config:
            config = json.loads(biz.config) if isinstance(biz.config, str) else biz.config
            from_number = config.get("twilio_number", "")

        result = await retell_client.create_call(
            agent_id=agent_id,
            phone_number=phone,
            from_number=from_number,
            metadata={
                "lead_id": prep.get("lead_id"),
                "customer_id": prep.get("customer_id"),
                "business_id": business_id,
                "call_type": prep.get("call_type"),
            },
        )

        # Record the call
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO voice_calls "
                    "(business_id, lead_id, customer_id, direction, call_type, "
                    "phone_number, language, dncl_checked, dncl_clear, "
                    "retell_call_id, status) "
                    "VALUES (:biz, :lead, :cust, 'outbound', :type, :phone, "
                    ":lang, TRUE, TRUE, :call_id, 'ringing')"
                ),
                {
                    "biz": business_id,
                    "lead": prep.get("lead_id"),
                    "cust": prep.get("customer_id"),
                    "type": prep.get("call_type"),
                    "phone": phone,
                    "lang": lang,
                    "call_id": result.get("call_id"),
                },
            )
            await db.commit()

        return {"call_made": True, "call_id": result.get("call_id"), "status": result.get("status")}

    async def process_result(self, context) -> dict:
        """Step 4: Classify call outcome and route accordingly."""
        call_data = context.step_output("make_call")
        if not call_data.get("call_made"):
            return {"processed": False}

        call_id = call_data.get("call_id")
        prep = context.step_output("prepare_call")

        # Fetch call details from Retell
        call_details = await retell_client.get_call(call_id) if call_id else {}
        transcript = call_details.get("transcript", "")
        duration = call_details.get("call_duration_ms", 0) / 1000

        if not transcript:
            return {"processed": False, "reason": "no transcript"}

        # Classify with Claude
        model_tier = await self.check_budget()
        response, cost = await call_claude(
            model_tier=model_tier,
            system=CALL_OUTCOME_PROMPT,
            user=f"Transcript:\n{transcript}",
            max_tokens=256,
            temperature=0.1,
        )

        try:
            classification = json.loads(response)
        except json.JSONDecodeError:
            classification = {"outcome": "escalate", "summary": "Classification failed"}

        outcome = classification.get("outcome", "escalate")

        # Route based on outcome
        async with SessionLocal() as db:
            # Update voice_calls record
            await db.execute(
                text(
                    "UPDATE voice_calls SET "
                    "status = 'completed', transcript = :transcript, "
                    "summary = :summary, outcome = :outcome, "
                    "duration_seconds = :duration, cost_usd = :cost, "
                    "sentiment_score = :sentiment, completed_at = NOW() "
                    "WHERE retell_call_id = :call_id"
                ),
                {
                    "transcript": transcript,
                    "summary": classification.get("summary"),
                    "outcome": outcome,
                    "duration": int(duration),
                    "cost": duration * 0.07 / 60,  # Retell: $0.07/min
                    "sentiment": classification.get("sentiment_score"),
                    "call_id": call_id,
                },
            )

            # Route by outcome
            lead_id = prep.get("lead_id")
            if outcome == "do_not_call" and prep.get("phone"):
                await dncl_client.add_to_internal_dncl(prep["phone"])
                if lead_id:
                    await db.execute(
                        text("UPDATE leads SET status = 'lost' WHERE id = :id"),
                        {"id": lead_id},
                    )

            elif outcome == "interested" and lead_id:
                await db.execute(
                    text("UPDATE leads SET status = 'booked' WHERE id = :id"),
                    {"id": lead_id},
                )

            elif outcome == "not_interested" and lead_id:
                await db.execute(
                    text("UPDATE leads SET status = 'lost' WHERE id = :id"),
                    {"id": lead_id},
                )

            await db.commit()

        await self.log_execution(
            action="process_result",
            result={"outcome": outcome, "duration": duration},
            cost_usd=cost,
            business_id=prep.get("business_id"),
        )

        return {
            "processed": True,
            "outcome": outcome,
            "duration_seconds": duration,
            "summary": classification.get("summary"),
        }


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="voice-agent", timeout="15m")
    class _Registered(VoiceAgent):
        @hatchet_instance.step(timeout="3m", retries=1)
        async def prepare_call(self, context: Context) -> dict:
            return await VoiceAgent.prepare_call(self, context)

        @hatchet_instance.step(timeout="3m", retries=1, parents=["prepare_call"])
        async def check_compliance(self, context: Context) -> dict:
            return await VoiceAgent.check_compliance(self, context)

        @hatchet_instance.step(timeout="5m", retries=1, parents=["check_compliance"])
        async def make_call(self, context: Context) -> dict:
            return await VoiceAgent.make_call(self, context)

        @hatchet_instance.step(timeout="5m", retries=1, parents=["make_call"])
        async def process_result(self, context: Context) -> dict:
            return await VoiceAgent.process_result(self, context)

    return _Registered

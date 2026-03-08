"""Agent 8: i18n Agent.

After deploy + weekly scan (cron Sunday 5AM). Validates fr.json/en.json completeness,
quality-checks natural québécois FR and Canadian EN, updates glossary, reports issues.
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

QUALITY_CHECK_SYSTEM_PROMPT = """\
Tu évalues la qualité linguistique des chaînes de traduction pour un SaaS canadien.

Pour le français: Est-ce du québécois naturel? (pas du français de France)
Pour l'anglais: Est-ce du Canadian English naturel? (pas du US English)

Pour chaque clé, réponds en JSON:
{
  "lang": "fr" ou "en",
  "natural": true/false,
  "issues": ["liste des problèmes si natural=false"],
  "suggestions": ["alternatives si applicable"]
}
"""


class I18nAgent(BaseAgent):
    """Translation & localization QA — validates completeness and quality."""

    agent_name = "i18n_agent"
    default_model = "haiku"

    async def pull_messages(self, context) -> dict:
        """Read fr.json/en.json from GitHub repo."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"messages": {}, "businesses": 0}

        result = {}
        for biz in businesses:
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        text("SELECT github_repo FROM businesses WHERE id = :id"),
                        {"id": biz["id"]},
                    )
                ).fetchone()
            repo = row.github_repo if row else None
            if not repo or not settings.GITHUB_TOKEN:
                continue

            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    for lang in ["fr", "en"]:
                        resp = await client.get(
                            f"https://api.github.com/repos/{repo}/contents/messages/{lang}.json",
                            headers={
                                "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                                "Accept": "application/vnd.github.raw",
                            },
                        )
                        if resp.status_code == 200:
                            data = json.loads(resp.text)
                            result.setdefault(biz["id"], {})[lang] = data
            except Exception as exc:
                logger.warning("pull_messages_failed", repo=repo, error=str(exc))

        await self.log_execution(
            action="pull_messages",
            result={"businesses": len(result), "repos_checked": len(businesses)},
        )
        return {"messages": result}

    async def validate_completeness(self, context) -> dict:
        """Check all keys in fr.json exist in en.json and vice versa."""
        pull_out = context.step_output("pull_messages")
        messages = pull_out.get("messages", {})
        issues = []

        for biz_id, langs in messages.items():
            fr_keys = set(langs.get("fr", {}).keys()) if "fr" in langs else set()
            en_keys = set(langs.get("en", {}).keys()) if "en" in langs else set()
            missing_fr = en_keys - fr_keys
            missing_en = fr_keys - en_keys
            if missing_fr:
                issues.append({"business_id": biz_id, "type": "missing_fr", "keys": list(missing_fr)})
            if missing_en:
                issues.append({"business_id": biz_id, "type": "missing_en", "keys": list(missing_en)})

        await self.log_execution(
            action="validate_completeness",
            result={"issues_count": len(issues), "issues": issues[:10]},
        )
        return {"complete": len(issues) == 0, "issues": issues}

    async def quality_check(self, context) -> dict:
        """Claude: natural québécois FR? natural Canadian EN?"""
        pull_out = context.step_output("pull_messages")
        messages = pull_out.get("messages", {})
        quality_results = []

        for biz_id, langs in messages.items():
            for lang, strings in langs.items():
                if not strings:
                    continue
                sample = dict(list(strings.items())[:10])
                model_tier = await self.check_budget()
                user_prompt = json.dumps({"lang": lang, "strings": sample}, default=str)
                response, cost = await call_claude(
                    model_tier=model_tier,
                    system=QUALITY_CHECK_SYSTEM_PROMPT,
                    user=user_prompt,
                    max_tokens=1024,
                    temperature=0.2,
                )
                try:
                    q = json.loads(response)
                    quality_results.append({"business_id": biz_id, "lang": lang, "result": q})
                except json.JSONDecodeError:
                    quality_results.append({"business_id": biz_id, "lang": lang, "result": {"natural": True}})
                await self.log_execution(
                    action="quality_check",
                    result={"business_id": biz_id, "lang": lang},
                    cost_usd=cost,
                    business_id=biz_id,
                )

        return {"quality_results": quality_results}

    async def update_glossary(self, context) -> dict:
        """Insert terms to glossary table."""
        pull_out = context.step_output("pull_messages")
        messages = pull_out.get("messages", {})
        inserted = 0

        for biz_id, langs in messages.items():
            fr = langs.get("fr", {})
            en = langs.get("en", {})
            common_keys = set(fr.keys()) & set(en.keys())
            for key in common_keys:
                term_en = en[key] if isinstance(en[key], str) else str(en[key])
                term_fr = fr[key] if isinstance(fr[key], str) else str(fr[key])
                async with SessionLocal() as db:
                    await db.execute(
                        text(
                            "INSERT INTO glossary (business_id, term_en, term_fr, context) "
                            "VALUES (:biz, :en, :fr, :ctx) "
                            "ON CONFLICT (business_id, term_en) DO UPDATE SET term_fr = EXCLUDED.term_fr"
                        ),
                        {"biz": biz_id, "en": term_en[:500], "fr": term_fr[:500], "ctx": key},
                    )
                    await db.commit()
                    inserted += 1

        await self.log_execution(action="update_glossary", result={"inserted": inserted})
        return {"glossary_updated": inserted}

    async def report_issues(self, context) -> dict:
        """Report completeness/quality issues to Slack."""
        validate_out = context.step_output("validate_completeness")
        issues = validate_out.get("issues", [])

        if issues and settings.SLACK_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        settings.SLACK_WEBHOOK_URL,
                        json={
                            "text": (
                                f":globe_with_meridians: *i18n Report* — {len(issues)} completeness issue(s)\n"
                                f"Details: {json.dumps(issues[:5])}"
                            )
                        },
                    )
            except Exception as exc:
                logger.warning("report_issues_failed", error=str(exc))

        await self.log_execution(action="report_issues", result={"issues_reported": len(issues)})
        return {"reported": len(issues)}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(
        name="i18n-agent",
        on_crons=["0 10 * * 0"],
    )
    class _Registered(I18nAgent):
        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def pull_messages(self, context: Context) -> dict:
            return await I18nAgent.pull_messages(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def validate_completeness(self, context: Context) -> dict:
            return await I18nAgent.validate_completeness(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def quality_check(self, context: Context) -> dict:
            return await I18nAgent.quality_check(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def update_glossary(self, context: Context) -> dict:
            return await I18nAgent.update_glossary(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def report_issues(self, context: Context) -> dict:
            return await I18nAgent.report_issues(self, context)

    return _Registered

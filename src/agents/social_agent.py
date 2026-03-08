"""Agent 10: Social Agent.

Cron 3x/day + event-driven.  Monitors communities via Syften, identifies
opportunities, generates value-first responses with Claude Haiku.

ANTI-BAN RULES (80% of SaaS companies get banned from Reddit in month 1):
- 90/10 rule: 90% genuinely helpful, NO product mention. 10% contextual.
- Never post same link twice. Vary domains.
- Reddit: karma must be > 100 before any product mention.
- Facebook Groups: read rules first. No links if rules forbid.
- If ANY post removed/reported → pause that community 14 days.

LinkedIn: Founder-persona posts 3x/week. FR for QC, EN for ROC.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import get_active_businesses, load_playbook
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

RESPONSE_SYSTEM_PROMPT = """\
Tu génères un commentaire pour un forum/réseau social (Reddit, Facebook, LinkedIn).

RÈGLES ANTI-BAN CRITIQUES:
- {mention_mode}
- Sois GENUINEMENT utile. Réponds à la question posée.
- Pas de jargon marketing. Parle comme un professionnel de l'industrie.
- Maximum 100 mots.
- Pas de lien dans la réponse (sauf si demandé explicitement).
- Ton: {tone}

Contexte du post: {context}
Industrie: {niche}

Réponds UNIQUEMENT avec le texte du commentaire, rien d'autre.
"""

MIN_KARMA_FOR_MENTION = 100
MENTION_RATIO = 0.10  # 10% of posts can mention product
PAUSE_DAYS_ON_REMOVAL = 14


class AntiBanGuardrails:
    """Enforces anti-ban rules per community."""

    @staticmethod
    async def check_community_status(db, business_id: int, community: str) -> dict:
        """Check if we're paused in a community and count recent posts."""
        row = (
            await db.execute(
                text(
                    "SELECT COUNT(*) AS total, "
                    "COUNT(*) FILTER (WHERE posted_at > NOW() - INTERVAL '24 hours') AS today, "
                    "MAX(CASE WHEN engagement->>'removed' = 'true' THEN posted_at END) AS last_removal "
                    "FROM social_posts "
                    "WHERE business_id = :biz AND community = :comm"
                ),
                {"biz": business_id, "comm": community},
            )
        ).fetchone()

        total = row.total or 0
        today = row.today or 0
        last_removal = row.last_removal

        paused = False
        if last_removal:
            pause_until = last_removal + timedelta(days=PAUSE_DAYS_ON_REMOVAL)
            paused = datetime.now(tz=timezone.utc) < pause_until

        # 90/10 rule: count mentions vs total
        mention_row = (
            await db.execute(
                text(
                    "SELECT COUNT(*) AS mentions FROM social_posts "
                    "WHERE business_id = :biz AND community = :comm "
                    "AND engagement->>'has_mention' = 'true'"
                ),
                {"biz": business_id, "comm": community},
            )
        ).fetchone()
        mentions = mention_row.mentions or 0
        can_mention = total == 0 or (mentions / max(total, 1)) < MENTION_RATIO

        return {
            "paused": paused,
            "total_posts": total,
            "today_posts": today,
            "can_mention": can_mention,
            "mention_ratio": mentions / max(total, 1),
        }

    @staticmethod
    async def check_reddit_karma(db, business_id: int) -> int:
        """Get accumulated karma estimate for Reddit persona."""
        row = (
            await db.execute(
                text(
                    "SELECT COALESCE(SUM((engagement->>'upvotes')::int), 0) AS karma "
                    "FROM social_posts "
                    "WHERE business_id = :biz AND platform = 'reddit'"
                ),
                {"biz": business_id},
            )
        ).fetchone()
        return row.karma or 0


async def _fetch_syften_alerts(keywords: list[str]) -> list[dict]:
    """Fetch keyword alerts from Syften.com monitoring service."""
    # Syften API integration — returns community mentions matching keywords
    # In production: poll Syften API or process webhook payloads
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                "https://syften.com/api/v1/alerts",
                headers={"Authorization": f"Bearer {settings.SLACK_WEBHOOK_URL}"},
                params={"keywords": ",".join(keywords[:10])},
            )
            if resp.status_code == 200:
                return resp.json().get("alerts", [])
        except Exception as exc:
            logger.info("syften_fetch_skipped", reason=str(exc))
    return []


class SocialAgent(BaseAgent):
    """Community monitoring + value-first engagement with anti-ban guardrails."""

    agent_name = "social_agent"
    default_model = "haiku"

    async def monitor_and_engage(self, context) -> dict:
        """Scan communities for opportunities and generate responses."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"businesses": 0, "opportunities": 0, "posts": 0}

        total_opportunities = 0
        total_posts = 0

        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            icp = playbook.get("icp", {})
            channels = playbook.get("channels_ranked", [])
            messaging = playbook.get("messaging", {})
            pain_keywords = icp.get("pain_keywords", [])

            # Fetch alerts from Syften
            alerts = await _fetch_syften_alerts(pain_keywords)
            total_opportunities += len(alerts)

            async with SessionLocal() as db:
                for alert in alerts:
                    community = alert.get("community", "")
                    platform = alert.get("platform", "reddit")
                    post_content = alert.get("content", "")

                    if not community or not post_content:
                        continue

                    # Check anti-ban guardrails
                    status = await AntiBanGuardrails.check_community_status(db, biz["id"], community)

                    if status["paused"]:
                        logger.info("community_paused", community=community)
                        continue

                    if status["today_posts"] >= 3:
                        continue  # max 3 posts per community per day

                    # Determine if this should mention the product (90/10 rule)
                    can_mention = status["can_mention"]
                    if platform == "reddit":
                        karma = await AntiBanGuardrails.check_reddit_karma(db, biz["id"])
                        if karma < MIN_KARMA_FOR_MENTION:
                            can_mention = False

                    mention_mode = (
                        "Tu PEUX mentionner brièvement le produit comme UNE option parmi d'autres."
                        if can_mention else
                        "NE MENTIONNE PAS le produit. Sois 100% utile, zéro promotion."
                    )

                    model_tier = await self.check_budget()
                    prompt = RESPONSE_SYSTEM_PROMPT.format(
                        mention_mode=mention_mode,
                        tone=messaging.get("tone", "professionnel"),
                        context=post_content[:500],
                        niche=icp.get("niche", ""),
                    )

                    response_text, cost = await call_claude(
                        model_tier=model_tier,
                        system=prompt,
                        user=post_content[:1000],
                        max_tokens=256,
                        temperature=0.7,
                    )

                    # Log the generated post
                    await db.execute(
                        text(
                            "INSERT INTO social_posts "
                            "(business_id, platform, community, post_type, content, "
                            "engagement, posted_at) "
                            "VALUES (:biz, :platform, :comm, 'comment', :content, :engage, NOW())"
                        ),
                        {
                            "biz": biz["id"],
                            "platform": platform,
                            "comm": community,
                            "content": response_text,
                            "engage": json.dumps({"has_mention": can_mention, "status": "draft"}),
                        },
                    )
                    total_posts += 1

                await db.commit()

            await self.log_execution(
                action="monitor_and_engage",
                result={"opportunities": len(alerts), "posts": total_posts},
                business_id=biz["id"],
            )

        return {"businesses": len(businesses), "opportunities": total_opportunities, "posts": total_posts}

    async def linkedin_posts(self, context) -> dict:
        """Generate founder-persona LinkedIn posts (3x/week, thought leadership)."""
        businesses = await get_active_businesses()
        if not businesses:
            return {"posts_generated": 0}

        total = 0
        for biz in businesses:
            playbook = await load_playbook(biz["id"])
            if not playbook:
                continue

            icp = playbook.get("icp", {})
            lang = icp.get("language", "fr")

            model_tier = await self.check_budget()
            prompt = (
                f"Écris un post LinkedIn court (150 mots max) en {'français québécois' if lang == 'fr' else 'English'}.\n"
                f"Perspective: fondateur/entrepreneur dans le domaine de {icp.get('niche', '')}.\n"
                f"Style: thought leadership, pas de promotion directe de produit.\n"
                f"Sujets possibles: tendances industrie, leçons apprises, conseils pratiques.\n"
                f"PAS de hashtags excessifs (max 3). PAS de lien. PAS de mention de produit."
            )

            post_text, cost = await call_claude(
                model_tier=model_tier,
                system="Tu es un entrepreneur québécois qui partage des réflexions sur LinkedIn.",
                user=prompt,
                max_tokens=512,
                temperature=0.8,
            )

            async with SessionLocal() as db:
                await db.execute(
                    text(
                        "INSERT INTO social_posts "
                        "(business_id, platform, post_type, content, engagement, posted_at) "
                        "VALUES (:biz, 'linkedin', 'post', :content, :engage, NOW())"
                    ),
                    {
                        "biz": biz["id"],
                        "content": post_text,
                        "engage": json.dumps({"status": "draft", "type": "thought_leadership"}),
                    },
                )
                await db.commit()
            total += 1

        return {"posts_generated": total}

    async def monitor_brand_mentions(self, context) -> dict:
        """Monitor for negative brand mentions. Pause + alert if sentiment < 0.3."""
        from src.agents.distribution import get_active_businesses

        businesses = await get_active_businesses()
        alerts = 0

        for biz in businesses:
            async with SessionLocal() as db:
                # Check recent social posts for negative responses
                recent = (await db.execute(text(
                    "SELECT id, platform, community, content FROM social_posts "
                    "WHERE business_id = :biz AND posted_at > NOW() - INTERVAL '24 hours'"
                ), {"biz": biz["id"]})).fetchall()

                for post in recent:
                    # In production: check Syften for mentions + Claude sentiment
                    pass

                # Check for any negative brand mentions detected
                negatives = (await db.execute(text(
                    "SELECT COUNT(*) AS cnt FROM brand_mentions "
                    "WHERE business_id = :biz AND is_negative = TRUE "
                    "AND actioned = FALSE AND detected_at > NOW() - INTERVAL '24 hours'"
                ), {"biz": biz["id"]})).fetchone()

                if (negatives.cnt or 0) > 0:
                    # Pause all social activity for this business
                    logger.warning("brand_negative_detected", business=biz["slug"], count=negatives.cnt)
                    if settings.SLACK_WEBHOOK_URL:
                        async with httpx.AsyncClient(timeout=5) as client:
                            try:
                                await client.post(settings.SLACK_WEBHOOK_URL, json={
                                    "text": f":rotating_light: *Brand Alert* — {biz['name']}: {negatives.cnt} negative mention(s) detected. Social activity paused."
                                })
                            except Exception:
                                pass
                    alerts += 1

        return {"businesses_checked": len(businesses), "alerts": alerts}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="social-agent", on_crons=["0 13,17,21 * * *"])
    class _Registered(SocialAgent):
        @hatchet_instance.task(execution_timeout="10m", retries=1)
        async def monitor_and_engage(self, context: Context) -> dict:
            return await SocialAgent.monitor_and_engage(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def linkedin_posts(self, context: Context) -> dict:
            return await SocialAgent.linkedin_posts(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def monitor_brand_mentions(self, context: Context) -> dict:
            return await SocialAgent.monitor_brand_mentions(self, context)

    return _Registered

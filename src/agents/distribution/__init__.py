"""Distribution Engine — 5 sub-agents that share the GTM Playbook config.

Changing verticals means changing the gtm_playbooks YAML config, not the code.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from src.db import SessionLocal

logger = structlog.get_logger()


async def load_playbook(business_id: int) -> dict | None:
    """Load the GTM Playbook config for a business from the database."""
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT config FROM gtm_playbooks WHERE business_id = :biz"),
                {"biz": business_id},
            )
        ).fetchone()
    if row and row.config:
        import json
        return json.loads(row.config) if isinstance(row.config, str) else row.config
    return None


async def get_active_businesses() -> list[dict]:
    """Return all businesses with status 'live' or 'pre_launch' that have a playbook."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT b.id, b.name, b.slug, b.domain "
                    "FROM businesses b "
                    "JOIN gtm_playbooks g ON g.business_id = b.id "
                    "WHERE b.status IN ('live', 'pre_launch') "
                    "ORDER BY b.id"
                )
            )
        ).fetchall()
    return [{"id": r.id, "name": r.name, "slug": r.slug, "domain": r.domain} for r in rows]

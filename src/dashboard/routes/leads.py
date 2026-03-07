"""Lead outreach approval — shadow mode approve/reject."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from src.dashboard.deps import verify_credentials
from src.db import SessionLocal

router = APIRouter(prefix="/leads")


@router.post("/{lead_id}/approve", response_class=HTMLResponse)
async def approve_outreach(lead_id: int, user: str = Depends(verify_credentials)):
    """CEO approved outreach — mark lead for send (placeholder for shadow mode)."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET notes = COALESCE(notes, '') || '\n[CEO approved]' WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()
    return HTMLResponse('<div class="text-green-400 text-sm py-2">✓ Approved</div>')


@router.post("/{lead_id}/reject", response_class=HTMLResponse)
async def reject_outreach(lead_id: int, user: str = Depends(verify_credentials)):
    """CEO rejected outreach — mark lead (placeholder for shadow mode)."""
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE leads SET notes = COALESCE(notes, '') || '\n[CEO rejected]' WHERE id = :id"),
            {"id": lead_id},
        )
        await db.commit()
    return HTMLResponse('<div class="text-red-400 text-sm py-2">✕ Rejected</div>')

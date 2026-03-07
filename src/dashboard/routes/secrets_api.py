"""Setup Wizard + Settings + Secrets API.

/setup       — first-time setup wizard (5 steps)
/settings    — ongoing secrets management
/api/secrets/test  — test a single API key connection
/api/secrets/save  — encrypt and upsert a secret
"""

from __future__ import annotations

import json
import secrets as _secrets
from datetime import datetime, timezone
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import text
from starlette.status import HTTP_401_UNAUTHORIZED

from src.config import settings
from src.crypto import decrypt, encrypt
from src.db import SessionLocal

logger = structlog.get_logger()

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(_security)):
    correct_user = _secrets.compare_digest(
        credentials.username.encode(), settings.DASHBOARD_USER.encode()
    )
    correct_pass = _secrets.compare_digest(
        credentials.password.encode(), settings.DASHBOARD_PASSWORD.encode()
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

router = APIRouter()

# ── Schema for every secret, organized by setup wizard step ──────────────

SECRETS_SCHEMA = [
    {
        "step": 1,
        "category": "core",
        "title": "Core",
        "description": "Required to do anything",
        "fields": [
            {"key": "ANTHROPIC_API_KEY", "name": "Anthropic API Key", "placeholder": "sk-ant-..."},
            {"key": "SERPER_API_KEY", "name": "Serper API Key", "placeholder": ""},
            {"key": "SLACK_WEBHOOK_URL", "name": "Slack Webhook URL", "placeholder": "https://hooks.slack.com/services/..."},
        ],
    },
    {
        "step": 2,
        "category": "lead_gen",
        "title": "Lead Generation",
        "description": "Required for the Distribution Engine",
        "fields": [
            {"key": "APOLLO_API_KEY", "name": "Apollo API Key", "placeholder": ""},
            {"key": "HUNTER_API_KEY", "name": "Hunter API Key", "placeholder": ""},
            {"key": "ZEROBOUNCE_API_KEY", "name": "ZeroBounce API Key", "placeholder": ""},
            {"key": "SPARKTORO_API_KEY", "name": "SparkToro API Key", "placeholder": ""},
        ],
    },
    {
        "step": 3,
        "category": "infrastructure",
        "title": "Infrastructure",
        "description": "Required to create businesses",
        "fields": [
            {"key": "NAMECHEAP_API_KEY", "name": "Namecheap API Key", "placeholder": ""},
            {"key": "NAMECHEAP_API_USER", "name": "Namecheap API User", "placeholder": ""},
            {"key": "CLOUDFLARE_API_TOKEN", "name": "Cloudflare API Token", "placeholder": ""},
            {"key": "VERCEL_TOKEN", "name": "Vercel Token", "placeholder": ""},
            {"key": "GITHUB_TOKEN", "name": "GitHub Token", "placeholder": "ghp_..."},
            {"key": "SUPABASE_ACCESS_TOKEN", "name": "Supabase Access Token", "placeholder": ""},
            {"key": "STRIPE_SECRET_KEY", "name": "Stripe Secret Key", "placeholder": "sk_test_..."},
        ],
    },
    {
        "step": 4,
        "category": "outreach",
        "title": "Outreach",
        "description": "Required to send emails and make calls",
        "fields": [
            {"key": "INSTANTLY_API_KEY", "name": "Instantly API Key", "placeholder": ""},
            {"key": "RESEND_API_KEY", "name": "Resend API Key", "placeholder": "re_..."},
            {"key": "TWILIO_ACCOUNT_SID", "name": "Twilio Account SID", "placeholder": "AC..."},
            {"key": "TWILIO_AUTH_TOKEN", "name": "Twilio Auth Token", "placeholder": ""},
            {"key": "TWILIO_PHONE_NUMBER", "name": "Twilio Phone Number", "placeholder": "+1..."},
            {"key": "RETELL_API_KEY", "name": "Retell API Key", "placeholder": ""},
            {"key": "REDDIT_CLIENT_ID", "name": "Reddit Client ID", "placeholder": ""},
            {"key": "REDDIT_CLIENT_SECRET", "name": "Reddit Client Secret", "placeholder": ""},
        ],
    },
    {
        "step": 5,
        "category": "optional",
        "title": "Optional",
        "description": "Enhance but not required",
        "fields": [
            {"key": "GOOGLE_ADS_DEVELOPER_TOKEN", "name": "Google Ads Developer Token", "placeholder": ""},
            {"key": "META_ADS_ACCESS_TOKEN", "name": "Meta Ads Access Token", "placeholder": ""},
            {"key": "DROPCONTACT_API_KEY", "name": "Dropcontact API Key", "placeholder": ""},
            {"key": "SENDGRID_API_KEY", "name": "SendGrid API Key", "placeholder": "SG..."},
        ],
    },
]


async def _get_configured_keys() -> dict[str, dict]:
    """Load all configured secrets (masked values + status) from DB."""
    try:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT key, display_name, is_configured, last_tested_at, "
                        "last_test_status, value_encrypted FROM secrets"
                    )
                )
            ).fetchall()
    except Exception:
        return {}

    result = {}
    for r in rows:
        masked = ""
        if r.value_encrypted:
            try:
                plain = decrypt(r.value_encrypted)
                masked = "•" * max(0, len(plain) - 4) + plain[-4:] if len(plain) > 4 else "••••"
            except Exception:
                masked = "••••"
        result[r.key] = {
            "name": r.display_name,
            "configured": r.is_configured,
            "masked": masked,
            "tested_at": r.last_tested_at.isoformat() if r.last_tested_at else None,
            "test_status": r.last_test_status or "untested",
        }
    return result


# ── Test functions for each API key ──────────────────────────────────────

async def _test_anthropic(value: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": value, "anthropic-version": "2023-06-01"},
        )
        return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "error": f"HTTP {resp.status_code}"}


async def _test_stripe(value: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            "https://api.stripe.com/v1/balance",
            headers={"Authorization": f"Bearer {value}"},
        )
        return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "error": f"HTTP {resp.status_code}"}


async def _test_slack(value: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(value, json={"text": ":white_check_mark: Factory connected!"})
        return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "error": f"HTTP {resp.status_code}"}


async def _test_vercel(value: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            "https://api.vercel.com/v2/user",
            headers={"Authorization": f"Bearer {value}"},
        )
        return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "error": f"HTTP {resp.status_code}"}


async def _test_github(value: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {value}", "Accept": "application/vnd.github+json"},
        )
        return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "error": f"HTTP {resp.status_code}"}


async def _test_generic(value: str) -> dict:
    return {"status": "ok"} if value and len(value) > 5 else {"status": "failed", "error": "Value too short"}


TEST_FUNCTIONS = {
    "ANTHROPIC_API_KEY": _test_anthropic,
    "STRIPE_SECRET_KEY": _test_stripe,
    "SLACK_WEBHOOK_URL": _test_slack,
    "VERCEL_TOKEN": _test_vercel,
    "GITHUB_TOKEN": _test_github,
}


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/setup", response_class=HTMLResponse)
async def setup_wizard(request: Request, step: int = 1, user: str = Depends(verify_credentials)):
    if settings.is_setup_complete():
        return RedirectResponse("/settings", status_code=302)

    total_steps = len(SECRETS_SCHEMA)
    if step < 1:
        return RedirectResponse("/setup?step=1", status_code=302)
    if step > total_steps:
        return RedirectResponse("/", status_code=302)

    configured = await _get_configured_keys()
    current = next((s for s in SECRETS_SCHEMA if s["step"] == step), SECRETS_SCHEMA[0])

    return templates.TemplateResponse("setup.html", {
        "request": request,
        "steps": SECRETS_SCHEMA,
        "current_step": current,
        "step": step,
        "total_steps": len(SECRETS_SCHEMA),
        "configured": configured,
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: str = Depends(verify_credentials)):
    configured = await _get_configured_keys()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "steps": SECRETS_SCHEMA,
        "configured": configured,
        "budget_limit": settings.DAILY_BUDGET_LIMIT_USD,
    })


class SecretTestRequest(BaseModel):
    key: str
    value: str


@router.post("/api/secrets/test", response_class=HTMLResponse)
async def test_secret(req: SecretTestRequest, user: str = Depends(verify_credentials)):
    """Test a single API key connection."""
    tester = TEST_FUNCTIONS.get(req.key, _test_generic)
    try:
        result = await tester(req.value)
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)}

    # Update test status in DB if the key exists
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE secrets SET last_tested_at = NOW(), "
                "last_test_status = :status WHERE key = :key"
            ),
            {"status": result["status"], "key": req.key},
        )
        await db.commit()

    if result["status"] == "ok":
        return HTMLResponse(
            '<span class="inline-flex items-center gap-1 text-green-400">'
            '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>'
            "Connected</span>"
        )
    error = result.get("error", "Unknown error")
    return HTMLResponse(
        f'<span class="inline-flex items-center gap-1 text-red-400">'
        f'<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>'
        f"Failed: {error}</span>"
    )


class SecretSaveRequest(BaseModel):
    key: str
    value: str
    category: str = "core"
    display_name: str = ""


@router.post("/api/secrets/save", response_class=HTMLResponse)
async def save_secret(req: SecretSaveRequest, user: str = Depends(verify_credentials)):
    """Encrypt and upsert a secret into the DB."""
    encrypted = encrypt(req.value)

    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO secrets (key, value_encrypted, category, display_name, "
                "is_configured, updated_at) "
                "VALUES (:key, :val, :cat, :name, TRUE, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET "
                "value_encrypted = EXCLUDED.value_encrypted, "
                "category = EXCLUDED.category, "
                "display_name = EXCLUDED.display_name, "
                "is_configured = TRUE, "
                "updated_at = NOW()"
            ),
            {
                "key": req.key,
                "val": encrypted,
                "cat": req.category,
                "name": req.display_name or req.key,
            },
        )
        await db.commit()

    # Invalidate cache so agents pick up the new value
    settings.invalidate(req.key)

    return HTMLResponse(
        '<span class="text-green-400 text-sm">Saved</span>'
    )


@router.post("/api/secrets/test-all", response_class=JSONResponse)
async def test_all_secrets(user: str = Depends(verify_credentials)):
    """Test all configured secrets using stored values."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT key, value_encrypted FROM secrets "
                    "WHERE is_configured = TRUE AND value_encrypted IS NOT NULL"
                )
            )
        ).fetchall()

    tested = 0
    for r in rows:
        try:
            plain = decrypt(r.value_encrypted)
        except Exception:
            continue
        tester = TEST_FUNCTIONS.get(r.key, _test_generic)
        try:
            result = await tester(plain)
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}

        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE secrets SET last_tested_at = NOW(), "
                    "last_test_status = :status WHERE key = :key"
                ),
                {"status": result["status"], "key": r.key},
            )
            await db.commit()
        tested += 1

    return JSONResponse({"tested": tested})

"""Shared dashboard dependencies — templates, auth via Supabase, session cookies.

Auth flow:
1. User submits email+password on /login
2. Server calls Supabase sign_in_with_password() to verify
3. On success, server sets an HMAC-signed session cookie (email:role:ts:sig)
4. Subsequent requests are verified via the cookie (no per-request Supabase call)
5. Invite: admin calls supabase.auth.admin.create_user() + inserts role into dashboard_users

Roles: admin (full control), operator (run+approve), viewer (read-only).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path

import structlog
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

logger = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "factory_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

ROLES = {
    "admin": {"can_kill": True, "can_edit_settings": True, "can_approve": True, "can_view": True},
    "operator": {"can_kill": False, "can_edit_settings": False, "can_approve": True, "can_view": True},
    "viewer": {"can_kill": False, "can_edit_settings": False, "can_approve": False, "can_view": True},
}


def _get_signing_key() -> bytes:
    encryption_key = os.environ.get("ENCRYPTION_KEY", "fallback-dev-key")
    return encryption_key.encode()


def _sign_token(email: str, role: str = "admin") -> str:
    """Create a signed session token: email:role:timestamp:signature."""
    ts = str(int(time.time()))
    payload = f"{email}:{role}:{ts}"
    sig = hmac.new(_get_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> dict | None:
    """Verify a signed session token. Returns {"username": str, "role": str} or None."""
    parts = token.split(":")
    if len(parts) != 4:
        return None
    username, role, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    if time.time() - ts > SESSION_MAX_AGE:
        return None
    expected = hmac.new(_get_signing_key(), f"{username}:{role}:{ts_str}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    return {"username": username, "role": role}


def get_current_user(request: Request) -> dict | None:
    """Extract and verify the session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return _verify_token(token)


def verify_credentials(request: Request) -> str:
    """Dependency: require authenticated user. Redirects to /login if not."""
    user = get_current_user(request)
    if not user:
        raise RedirectResponse("/login", status_code=302)
    return user["username"]


# ── Supabase Auth ────────────────────────────────────────────────────────────


def _get_supabase_client():
    """Get a Supabase client using the service role key (admin operations)."""
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def check_password(email: str, password: str) -> dict | None:
    """Verify credentials via Supabase Auth. Returns {"username", "role"} or None."""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.error("supabase_not_configured")
        return None

    try:
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        response = client.auth.sign_in_with_password({"email": email, "password": password})

        if response.user:
            role = _get_user_role(email)
            return {"username": email, "role": role}
    except Exception as exc:
        logger.warning("supabase_auth_failed", email=email, error=str(exc))

    return None


def _get_user_role(email: str) -> str:
    """Look up user role from dashboard_users table. First user defaults to admin."""
    try:
        import sqlalchemy
        from src.config import DATABASE_URL

        sync_url = DATABASE_URL.replace("+asyncpg", "")
        engine = sqlalchemy.create_engine(sync_url)
        with engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text(
                    "SELECT role FROM dashboard_users WHERE email = :email AND is_active = TRUE"
                ),
                {"email": email},
            ).fetchone()
            if row:
                conn.execute(
                    sqlalchemy.text("UPDATE dashboard_users SET last_login_at = NOW() WHERE email = :email"),
                    {"email": email},
                )
                conn.commit()
                return row.role

            # First user ever → auto-assign admin and insert
            count = conn.execute(sqlalchemy.text("SELECT COUNT(*) AS cnt FROM dashboard_users")).fetchone()
            role = "admin" if (count.cnt or 0) == 0 else "viewer"
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO dashboard_users (email, password_hash, name, role) "
                    "VALUES (:email, 'supabase_managed', :email, :role) "
                    "ON CONFLICT (email) DO NOTHING"
                ),
                {"email": email, "role": role},
            )
            conn.commit()
            return role
    except Exception as exc:
        logger.warning("role_lookup_failed", email=email, error=str(exc))
        return "admin"


async def create_user(*, email: str, password: str, name: str = "", role: str = "viewer") -> bool:
    """Invite a new user: create in Supabase Auth + insert role into dashboard_users."""
    try:
        sb = _get_supabase_client()
        if not sb:
            logger.error("supabase_service_role_not_configured")
            return False

        sb.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
        })

        from sqlalchemy import text as sa_text
        from src.db import SessionLocal

        async with SessionLocal() as db:
            await db.execute(
                sa_text(
                    "INSERT INTO dashboard_users (email, password_hash, name, role) "
                    "VALUES (:email, 'supabase_managed', :name, :role) "
                    "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role"
                ),
                {"email": email, "name": name or email, "role": role},
            )
            await db.commit()

        logger.info("user_invited", email=email, role=role)
        return True
    except Exception as exc:
        logger.error("user_invite_failed", email=email, error=str(exc))
        return False


async def list_users() -> list[dict]:
    """List all dashboard users."""
    try:
        from sqlalchemy import text as sa_text
        from src.db import SessionLocal

        async with SessionLocal() as db:
            rows = (await db.execute(sa_text(
                "SELECT id, email, name, role, is_active, last_login_at, created_at "
                "FROM dashboard_users ORDER BY created_at"
            ))).fetchall()
        return [
            {"id": r.id, "email": r.email, "name": r.name, "role": r.role,
             "active": r.is_active, "last_login": r.last_login_at, "created": r.created_at}
            for r in rows
        ]
    except Exception:
        return []

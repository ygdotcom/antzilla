"""Shared dashboard dependencies — templates, auth, session management.

Uses signed cookies for sessions. Supports two auth modes:
1. Bootstrap admin: DASHBOARD_USER/DASHBOARD_PASSWORD from .env (always works)
2. Database users: dashboard_users table with bcrypt-hashed passwords + roles

Roles: admin (full control), operator (run agents, manage businesses),
       viewer (read-only dashboards).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.config import settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "factory_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

ROLES = {
    "admin": {"can_kill": True, "can_edit_settings": True, "can_approve": True, "can_view": True},
    "operator": {"can_kill": False, "can_edit_settings": False, "can_approve": True, "can_view": True},
    "viewer": {"can_kill": False, "can_edit_settings": False, "can_approve": False, "can_view": True},
}


def _get_signing_key() -> bytes:
    return (settings.ENCRYPTION_KEY or "fallback-dev-key").encode()


def _sign_token(username: str, role: str = "admin") -> str:
    """Create a signed session token: username:role:timestamp:signature."""
    ts = str(int(time.time()))
    payload = f"{username}:{role}:{ts}"
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
    """Extract and verify the session cookie. Returns {"username", "role"} or None."""
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


def check_password(username: str, password: str) -> dict | None:
    """Verify login credentials. Returns {"username", "role"} or None.

    Checks database users first, then falls back to .env bootstrap admin.
    """
    # 1. Try database users
    db_user = _check_db_user(username, password)
    if db_user:
        return db_user

    # 2. Fallback: bootstrap admin from .env
    import secrets as _secrets
    if (_secrets.compare_digest(username, settings.DASHBOARD_USER)
            and _secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)):
        return {"username": username, "role": "admin"}

    return None


def _check_db_user(email: str, password: str) -> dict | None:
    """Check credentials against dashboard_users table."""
    try:
        import bcrypt
        import sqlalchemy
        from src.config import DATABASE_URL

        sync_url = DATABASE_URL.replace("+asyncpg", "")
        engine = sqlalchemy.create_engine(sync_url)
        with engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text(
                    "SELECT email, password_hash, name, role FROM dashboard_users "
                    "WHERE email = :email AND is_active = TRUE"
                ),
                {"email": email},
            ).fetchone()
            if row and bcrypt.checkpw(password.encode(), row.password_hash.encode()):
                conn.execute(
                    sqlalchemy.text("UPDATE dashboard_users SET last_login_at = NOW() WHERE email = :email"),
                    {"email": email},
                )
                conn.commit()
                return {"username": row.email, "role": row.role, "name": row.name}
    except Exception:
        pass
    return None


async def create_user(*, email: str, password: str, name: str = "", role: str = "viewer") -> bool:
    """Create a new dashboard user with bcrypt-hashed password."""
    try:
        import bcrypt
        from sqlalchemy import text as sa_text
        from src.db import SessionLocal

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        async with SessionLocal() as db:
            await db.execute(
                sa_text(
                    "INSERT INTO dashboard_users (email, password_hash, name, role) "
                    "VALUES (:email, :pw, :name, :role) "
                    "ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, "
                    "name = EXCLUDED.name, role = EXCLUDED.role"
                ),
                {"email": email, "pw": pw_hash, "name": name, "role": role},
            )
            await db.commit()
        return True
    except Exception:
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

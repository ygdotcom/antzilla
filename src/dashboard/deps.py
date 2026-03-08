"""Shared dashboard dependencies — templates, auth, session management.

Uses signed cookies for session auth instead of HTTP Basic Auth.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from src.config import settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "factory_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


def _sign_token(username: str) -> str:
    """Create a signed session token: username:timestamp:signature."""
    ts = str(int(time.time()))
    key = (settings.ENCRYPTION_KEY or "fallback-dev-key").encode()
    payload = f"{username}:{ts}"
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> str | None:
    """Verify a signed session token. Returns username or None."""
    parts = token.split(":")
    if len(parts) != 3:
        return None
    username, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    if time.time() - ts > SESSION_MAX_AGE:
        return None
    key = (settings.ENCRYPTION_KEY or "fallback-dev-key").encode()
    expected = hmac.new(key, f"{username}:{ts_str}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    return username


def get_current_user(request: Request) -> str | None:
    """Extract and verify the session cookie. Returns username or None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return _verify_token(token)


def verify_credentials(request: Request) -> str:
    """Dependency: require authenticated user. Redirects to /login if not."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )
    return user


def check_password(username: str, password: str) -> bool:
    """Verify login credentials."""
    correct_user = secrets.compare_digest(username, settings.DASHBOARD_USER)
    correct_pass = secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)
    return correct_user and correct_pass

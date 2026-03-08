"""CEO Dashboard — FastAPI + HTMX + Tailwind.

Auth via Supabase (email/password). Session stored in HMAC-signed cookie.
First boot: /login → /setup wizard if no secrets configured.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.dashboard.deps import (
    SESSION_COOKIE,
    _sign_token,
    check_password,
    get_current_user,
    templates,
    verify_credentials,
)

logger = structlog.get_logger()

app = FastAPI(title="Factory Dashboard", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect to /login if not authenticated. Then to /setup if not configured."""

    async def dispatch(self, request, call_next):
        path = request.url.path

        if path.startswith(("/login", "/static")):
            return await call_next(request)

        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)

        if not path.startswith(("/setup", "/api/secrets", "/logout")):
            try:
                if not settings.is_setup_complete():
                    return RedirectResponse("/setup", status_code=302)
            except Exception:
                return RedirectResponse("/setup", status_code=302)

        return await call_next(request)


app.add_middleware(AuthMiddleware)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user_info = check_password(username, password)
    if user_info:
        token = _sign_token(user_info["username"], user_info.get("role", "admin"))
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=86400 * 7)
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid email or password."},
        status_code=401,
    )


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


from src.dashboard.routes import overview, businesses, agents, budget, decisions, ideas, knowledge, leads, secrets_api

app.include_router(overview.router)
app.include_router(businesses.router)
app.include_router(agents.router)
app.include_router(budget.router)
app.include_router(decisions.router)
app.include_router(ideas.router)
app.include_router(knowledge.router)
app.include_router(leads.router)
app.include_router(secrets_api.router)


@app.get("/businesses")
async def businesses_list(user: str = Depends(verify_credentials)):
    return RedirectResponse("/", status_code=302)


def start():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)


if __name__ == "__main__":
    start()

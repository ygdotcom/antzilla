"""CEO Dashboard — FastAPI + HTMX + Tailwind.

The only human interface to the factory. Everything else is autonomous.
Vercel-inspired dark design. Protected by basic auth.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_401_UNAUTHORIZED

from src.config import settings

logger = structlog.get_logger()

app = FastAPI(title="Factory Dashboard", docs_url=None, redoc_url=None)

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

security = HTTPBasic()

DASHBOARD_USER = getattr(settings, "DASHBOARD_USER", None) or "admin"
DASHBOARD_PASSWORD = getattr(settings, "DASHBOARD_PASSWORD", None) or "factory"


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username.encode(), DASHBOARD_USER.encode())
    correct_pass = secrets.compare_digest(credentials.password.encode(), DASHBOARD_PASSWORD.encode())
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


# Import and include route modules
from src.dashboard.routes import overview, businesses, agents, budget, decisions, ideas, leads


@app.get("/businesses")
async def businesses_list(user: str = Depends(verify_credentials)):
    """Redirect to overview (businesses table lives there)."""
    return RedirectResponse("/", status_code=302)


app.include_router(overview.router)
app.include_router(businesses.router)
app.include_router(agents.router)
app.include_router(budget.router)
app.include_router(decisions.router)
app.include_router(ideas.router)
app.include_router(leads.router)


def start():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)


if __name__ == "__main__":
    start()

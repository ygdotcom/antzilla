"""CEO Dashboard — FastAPI + HTMX + Tailwind.

The only human interface to the factory. Everything else is autonomous.
Vercel-inspired dark design. Protected by basic auth.
First boot: redirects to /setup wizard if no secrets configured.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.dashboard.deps import verify_credentials

logger = structlog.get_logger()

app = FastAPI(title="Factory Dashboard", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SetupRedirectMiddleware(BaseHTTPMiddleware):
    """If secrets table is empty, redirect all pages to /setup."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        skip = path.startswith(("/setup", "/api/secrets", "/static"))
        if not skip:
            try:
                if not settings.is_setup_complete():
                    return RedirectResponse("/setup", status_code=302)
            except Exception:
                return RedirectResponse("/setup", status_code=302)
        return await call_next(request)


app.add_middleware(SetupRedirectMiddleware)

# Import and include route modules
from src.dashboard.routes import overview, businesses, agents, budget, decisions, ideas, leads, secrets_api

app.include_router(overview.router)
app.include_router(businesses.router)
app.include_router(agents.router)
app.include_router(budget.router)
app.include_router(decisions.router)
app.include_router(ideas.router)
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

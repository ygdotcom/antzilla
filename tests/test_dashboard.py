"""Tests for the CEO Dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixture: test client with auth ────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_setup_complete():
    """All dashboard tests assume setup is complete (no /setup redirect)."""
    with patch("src.config.Settings.is_setup_complete", return_value=True):
        yield


@pytest.fixture
def client():
    from src.dashboard.app import app
    return TestClient(app)


def _login(client) -> dict:
    """Log in and return cookies dict for authenticated requests."""
    os.environ.setdefault("ENCRYPTION_KEY", "a" * 64)
    with patch("src.dashboard.app.check_password", return_value={"username": "test@test.com", "role": "admin"}):
        resp = client.post("/login", data={"username": "test@test.com", "password": "test"}, follow_redirects=False)
    return dict(resp.cookies)


@pytest.fixture
def auth_cookies(client):
    return _login(client)


@pytest.fixture
def auth_headers():
    """Backwards compat — returns empty dict since we use cookies now."""
    return {}


# ── Auth Tests ────────────────────────────────────────────────────────────────


class TestAuth:
    def test_no_auth_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("location", "")

    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "Sign in" in resp.text

    def test_bad_login_shows_error(self, client):
        with patch("src.dashboard.app.check_password", return_value=None):
            resp = client.post("/login", data={"username": "wrong", "password": "wrong"})
        assert resp.status_code == 401
        assert "Invalid" in resp.text

    def test_good_login_sets_cookie(self, client):
        os.environ.setdefault("ENCRYPTION_KEY", "a" * 64)
        with patch("src.dashboard.app.check_password", return_value={"username": "test@test.com", "role": "admin"}):
            resp = client.post("/login", data={"username": "test@test.com", "password": "test"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "factory_session" in resp.cookies

    def test_authenticated_request_succeeds(self, client, auth_cookies):
        with patch("src.dashboard.routes.overview._get_overview_data", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "total_mrr": 0, "customers_active": 0, "customers_new_7d": 0,
                "customers_churned_7d": 0, "leads_pipeline": 0,
                "spend_today": 0, "spend_month": 0, "budget_daily": 50,
                "agent_runs_today": 0, "agent_success_rate": 0, "agent_errors_today": 0,
                "businesses": [], "improvements": [],
            }
            resp = client.get("/", cookies=auth_cookies)
        assert resp.status_code == 200

    def test_logout_clears_cookie(self, client, auth_cookies):
        resp = client.get("/logout", cookies=auth_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("location", "")


# ── Template Existence Tests ──────────────────────────────────────────────────


class TestTemplates:
    def test_all_templates_exist(self):
        template_dir = Path(__file__).parent.parent / "src" / "dashboard" / "templates"
        required = ["base.html", "overview.html", "business.html", "agents.html",
                     "budget.html", "decisions.html", "ideas.html", "idea_detail.html"]
        for name in required:
            assert (template_dir / name).exists(), f"Missing template: {name}"


# ── Route Tests ───────────────────────────────────────────────────────────────


class TestOverviewRoute:
    def test_returns_html(self, client, auth_cookies):
        with patch("src.dashboard.routes.overview._get_overview_data", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "total_mrr": 1500.0, "customers_active": 15, "customers_new_7d": 3,
                "customers_churned_7d": 1, "leads_pipeline": 42,
                "spend_today": 12.5, "spend_month": 380.0, "budget_daily": 50,
                "agent_runs_today": 150, "agent_success_rate": 95.3, "agent_errors_today": 7,
                "businesses": [
                    {"id": 1, "name": "Toîturo", "slug": "toituro", "status": "live",
                     "mrr": 1500, "customers": 15, "kill_score": 72.5},
                ],
                "improvements": [
                    {"agent": "content_engine", "description": "Increase posting frequency", "priority": "high"},
                ],
            }
            resp = client.get("/", cookies=auth_cookies)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Factory" in resp.text


class TestBusinessRoutes:
    def test_controls_endpoint_exists(self, client, auth_cookies):
        with patch("src.dashboard.routes.businesses._get_business_data", new_callable=AsyncMock, return_value=None):
            resp = client.get("/business/nonexistent", cookies=auth_cookies)
        assert resp.status_code in (200, 404)


class TestAgentRoutes:
    def test_agents_page(self, client, auth_cookies):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.agents.SessionLocal", return_value=mock_db):
            resp = client.get("/agents", cookies=auth_cookies)
        assert resp.status_code == 200


class TestBudgetRoutes:
    def test_budget_page(self, client, auth_cookies):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        zero_result = MagicMock()
        zero_result.total = 0
        mock_db.execute = AsyncMock(return_value=MagicMock(
            fetchall=MagicMock(return_value=[]),
            fetchone=MagicMock(return_value=zero_result),
        ))

        with patch("src.dashboard.routes.budget.SessionLocal", return_value=mock_db):
            resp = client.get("/budget", cookies=auth_cookies)
        assert resp.status_code == 200


class TestDecisionRoutes:
    def test_decisions_page(self, client, auth_cookies):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.decisions.SessionLocal", return_value=mock_db):
            resp = client.get("/decisions", cookies=auth_cookies)
        assert resp.status_code == 200


class TestIdeaRoutes:
    def test_ideas_page(self, client, auth_cookies):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.ideas.SessionLocal", return_value=mock_db):
            resp = client.get("/ideas", cookies=auth_cookies)
        assert resp.status_code == 200


# ── Critical Controls Tests ──────────────────────────────────────────────────


class TestCriticalControls:
    """Verify all spec-required controls exist in the route handlers."""

    def test_kill_endpoint_exists(self):
        from src.dashboard.routes.businesses import router
        paths = [r.path for r in router.routes]
        assert any("kill" in p for p in paths)

    def test_double_down_endpoint_exists(self):
        from src.dashboard.routes.businesses import router
        paths = [r.path for r in router.routes]
        assert any("double-down" in p for p in paths)

    def test_controls_endpoint_exists(self):
        from src.dashboard.routes.businesses import router
        paths = [r.path for r in router.routes]
        assert any("controls" in p for p in paths)

    def test_proposal_approve_exists(self):
        from src.dashboard.routes.agents import router
        paths = [r.path for r in router.routes]
        assert any("approve" in p for p in paths)

    def test_proposal_reject_exists(self):
        from src.dashboard.routes.agents import router
        paths = [r.path for r in router.routes]
        assert any("reject" in p for p in paths)

    def test_throttle_all_exists(self):
        from src.dashboard.routes.budget import router
        paths = [r.path for r in router.routes]
        assert any("throttle-all" in p for p in paths)

    def test_pause_nonessential_exists(self):
        from src.dashboard.routes.budget import router
        paths = [r.path for r in router.routes]
        assert any("pause-nonessential" in p for p in paths)

    def test_idea_advance_exists(self):
        from src.dashboard.routes.ideas import router
        paths = [r.path for r in router.routes]
        assert any("advance" in p for p in paths)

    def test_idea_archive_exists(self):
        from src.dashboard.routes.ideas import router
        paths = [r.path for r in router.routes]
        assert any("archive" in p for p in paths)


class TestOutreachApprovalQueue:
    """The outreach approval queue shows pending messages during shadow mode."""

    def test_decisions_template_references_outreach_queue(self):
        template = (Path(__file__).parent.parent / "src" / "dashboard" / "templates" / "decisions.html").read_text()
        assert "outreach" in template.lower()

    def test_business_template_references_outreach_queue(self):
        template = (Path(__file__).parent.parent / "src" / "dashboard" / "templates" / "business.html").read_text()
        assert "outreach" in template.lower() or "pending" in template.lower()

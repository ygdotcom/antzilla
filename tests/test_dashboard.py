"""Tests for the CEO Dashboard."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixture: test client with auth ────────────────────────────────────────────


@pytest.fixture
def client():
    from src.dashboard.app import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    creds = base64.b64encode(b"admin:factory").decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def bad_auth_headers():
    creds = base64.b64encode(b"wrong:wrong").decode()
    return {"Authorization": f"Basic {creds}"}


# ── Auth Tests ────────────────────────────────────────────────────────────────


class TestAuth:
    def test_no_auth_returns_401(self, client):
        resp = client.get("/")
        assert resp.status_code == 401

    def test_bad_auth_returns_401(self, client, bad_auth_headers):
        resp = client.get("/", headers=bad_auth_headers)
        assert resp.status_code == 401

    def test_good_auth_succeeds(self, client, auth_headers):
        with patch("src.dashboard.routes.overview._get_overview_data", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "total_mrr": 0, "customers_active": 0, "customers_new_7d": 0,
                "customers_churned_7d": 0, "leads_pipeline": 0,
                "spend_today": 0, "spend_month": 0, "budget_daily": 50,
                "agent_runs_today": 0, "agent_success_rate": 0, "agent_errors_today": 0,
                "businesses": [], "improvements": [],
            }
            resp = client.get("/", headers=auth_headers)
        assert resp.status_code == 200


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
    def test_returns_html(self, client, auth_headers):
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
            resp = client.get("/", headers=auth_headers)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Factory" in resp.text


class TestBusinessRoutes:
    def test_controls_endpoint_exists(self, client, auth_headers):
        with patch("src.dashboard.routes.businesses._get_business_data", new_callable=AsyncMock, return_value=None):
            resp = client.get("/business/nonexistent", headers=auth_headers)
        assert resp.status_code in (200, 404)


class TestAgentRoutes:
    def test_agents_page(self, client, auth_headers):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.agents.SessionLocal", return_value=mock_db):
            resp = client.get("/agents", headers=auth_headers)
        assert resp.status_code == 200


class TestBudgetRoutes:
    def test_budget_page(self, client, auth_headers):
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
            resp = client.get("/budget", headers=auth_headers)
        assert resp.status_code == 200


class TestDecisionRoutes:
    def test_decisions_page(self, client, auth_headers):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.decisions.SessionLocal", return_value=mock_db):
            resp = client.get("/decisions", headers=auth_headers)
        assert resp.status_code == 200


class TestIdeaRoutes:
    def test_ideas_page(self, client, auth_headers):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.dashboard.routes.ideas.SessionLocal", return_value=mock_db):
            resp = client.get("/ideas", headers=auth_headers)
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

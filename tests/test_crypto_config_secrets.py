"""Tests for crypto, config, and secrets API."""

from __future__ import annotations


import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══ CRYPTO ═══════════════════════════════════════════════════════════════════


class TestCrypto:
    @pytest.fixture(autouse=True)
    def set_key(self):
        os.environ["ENCRYPTION_KEY"] = "a" * 64  # 32 bytes as hex
        yield
        os.environ.pop("ENCRYPTION_KEY", None)

    def test_encrypt_decrypt_roundtrip(self):
        from src.crypto import decrypt, encrypt
        original = "sk-ant-api03-secret-key-12345"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == original

    def test_encrypted_is_hex(self):
        from src.crypto import encrypt
        encrypted = encrypt("test")
        int(encrypted, 16)  # should not raise

    def test_different_encryptions_differ(self):
        from src.crypto import encrypt
        e1 = encrypt("same-value")
        e2 = encrypt("same-value")
        assert e1 != e2  # different nonces

    def test_decrypt_wrong_key_fails(self):
        from src.crypto import encrypt
        encrypted = encrypt("secret")
        os.environ["ENCRYPTION_KEY"] = "b" * 64
        from src.crypto import decrypt
        with pytest.raises(Exception):
            decrypt(encrypted)

    def test_missing_key_raises(self):
        os.environ.pop("ENCRYPTION_KEY", None)
        # Need to reimport to clear module-level state
        from src.crypto import _get_key
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
            _get_key()

    def test_short_key_raises(self):
        os.environ["ENCRYPTION_KEY"] = "abc"
        from src.crypto import _get_key
        with pytest.raises(RuntimeError):
            _get_key()


# ═══ CONFIG ═══════════════════════════════════════════════════════════════════


class TestSettings:
    def test_get_returns_env_var(self):
        os.environ["TEST_KEY_XYZ"] = "test_value"
        from src.config import Settings
        s = Settings()
        assert s.get("TEST_KEY_XYZ") == "test_value"
        os.environ.pop("TEST_KEY_XYZ")

    def test_get_returns_default_when_missing(self):
        from src.config import Settings
        s = Settings()
        assert s.get("NONEXISTENT_KEY_ABC", "fallback") == "fallback"

    def test_attribute_access_uses_get(self):
        os.environ["TEST_ATTR_KEY"] = "attr_val"
        from src.config import Settings
        s = Settings()
        assert s.TEST_ATTR_KEY == "attr_val"
        os.environ.pop("TEST_ATTR_KEY")

    def test_cache_invalidation(self):
        os.environ["CACHE_TEST"] = "v1"
        from src.config import Settings
        s = Settings()
        assert s.get("CACHE_TEST") == "v1"

        os.environ["CACHE_TEST"] = "v2"
        # Still cached
        assert s.get("CACHE_TEST") == "v1"
        # After invalidation
        s.invalidate("CACHE_TEST")
        assert s.get("CACHE_TEST") == "v2"
        os.environ.pop("CACHE_TEST")

    def test_boot_properties(self):
        from src.config import Settings
        s = Settings()
        assert isinstance(s.DASHBOARD_USER, str)
        assert isinstance(s.DAILY_BUDGET_LIMIT_USD, float)


# ═══ SECRETS API ══════════════════════════════════════════════════════════════


@pytest.fixture
def client():
    from src.dashboard.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def auth_cookies(client):
    import os; os.environ.setdefault("ENCRYPTION_KEY", "a" * 64)
    resp = client.post("/login", data={"username": "admin", "password": "factory"}, follow_redirects=False); return dict(resp.cookies)


class TestSecretsSchema:
    def test_schema_has_5_steps(self):
        from src.dashboard.routes.secrets_api import SECRETS_SCHEMA
        assert len(SECRETS_SCHEMA) == 5

    def test_step_categories(self):
        from src.dashboard.routes.secrets_api import SECRETS_SCHEMA
        categories = [s["category"] for s in SECRETS_SCHEMA]
        assert categories == ["core", "lead_gen", "infrastructure", "outreach", "optional"]

    def test_anthropic_in_core(self):
        from src.dashboard.routes.secrets_api import SECRETS_SCHEMA
        core_keys = [k["key"] for k in SECRETS_SCHEMA[0]["fields"]]
        assert "ANTHROPIC_API_KEY" in core_keys

    def test_stripe_in_infrastructure(self):
        from src.dashboard.routes.secrets_api import SECRETS_SCHEMA
        infra_keys = [k["key"] for k in SECRETS_SCHEMA[2]["fields"]]
        assert "STRIPE_SECRET_KEY" in infra_keys


class TestSetupWizard:
    def test_setup_page_loads(self, client, auth_cookies):
        with patch("src.config.Settings.is_setup_complete", return_value=False):
            with patch("src.dashboard.routes.secrets_api._get_configured_keys", new_callable=AsyncMock, return_value={}):
                resp = client.get("/setup", cookies=auth_cookies)
        assert resp.status_code == 200

    def test_setup_redirects_to_settings_when_configured(self, client, auth_cookies):
        with patch("src.config.Settings.is_setup_complete", return_value=True):
            resp = client.get("/setup", cookies=auth_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert "/settings" in resp.headers.get("location", "")


class TestSettingsPage:
    def test_settings_page_loads(self, client):
        with (
            patch("src.config.Settings.is_setup_complete", return_value=True),
            patch("src.dashboard.routes.secrets_api._get_configured_keys", new_callable=AsyncMock, return_value={}),
        ):
            resp = client.get("/settings", )
        assert resp.status_code == 200


class TestSecretsSaveEndpoint:
    def test_save_secret(self, client, auth_cookies):
        os.environ["ENCRYPTION_KEY"] = "a" * 64

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.config.Settings.is_setup_complete", return_value=True),
            patch("src.dashboard.routes.secrets_api.SessionLocal", return_value=mock_db),
        ):
            resp = client.post(
                "/api/secrets/save",
                json={"key": "TEST_KEY", "value": "test_value", "category": "core", "display_name": "Test"},
                cookies=auth_cookies,
            )
        assert resp.status_code == 200
        assert "Saved" in resp.text
        os.environ.pop("ENCRYPTION_KEY", None)


class TestSecretsTestEndpoint:
    def test_test_generic_key(self, client, auth_cookies):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.config.Settings.is_setup_complete", return_value=True),
            patch("src.dashboard.routes.secrets_api.SessionLocal", return_value=mock_db),
        ):
            resp = client.post(
                "/api/secrets/test",
                json={"key": "SOME_API_KEY", "value": "a_long_enough_value_here"},
                cookies=auth_cookies,
            )
        assert resp.status_code == 200
        assert "Connected" in resp.text


class TestSetupRedirect:
    """If secrets table is empty, redirect non-setup pages to /setup."""

    def test_overview_redirects_when_not_configured(self, client, auth_cookies):
        with patch("src.config.Settings.is_setup_complete", return_value=False):
            resp = client.get("/", cookies=auth_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert "/setup" in resp.headers.get("location", "")

    def test_setup_does_not_redirect(self, client):
        with (
            patch("src.config.Settings.is_setup_complete", return_value=False),
            patch("src.dashboard.routes.secrets_api._get_configured_keys", new_callable=AsyncMock, return_value={}),
        ):
            resp = client.get("/setup", )
        assert resp.status_code == 200


class TestMigrationHasSecretsTable:
    def test_secrets_table_in_migration(self):
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        assert "CREATE TABLE secrets" in sql
        assert "value_encrypted" in sql
        assert "category" in sql
        assert "last_test_status" in sql

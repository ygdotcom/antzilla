"""Settings — DB-first secrets with .env fallback.

API keys are stored encrypted in the `secrets` table and managed via the
CEO Dashboard.  The .env file only contains 6 boot variables that Docker
Compose needs before Postgres is available.

Usage in any agent or integration:
    from src.config import settings
    api_key = settings.get("ANTHROPIC_API_KEY")
"""

from __future__ import annotations

import os
import threading

import structlog

logger = structlog.get_logger()

# Boot-time variables read directly from environment (before DB is available)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://factory:changeme@localhost:5432/factory",
)
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "changeme")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "factory")
DAILY_BUDGET_LIMIT_USD = float(os.environ.get("DAILY_BUDGET_LIMIT_USD", "50.0"))
AGENT_DEFAULT_DAILY_LIMIT_USD = float(os.environ.get("AGENT_DEFAULT_DAILY_LIMIT_USD", "5.0"))


class Settings:
    """Reads secrets from the DB (encrypted), falls back to os.environ.

    Thread-safe in-memory cache.  Call invalidate() to force a re-read.
    """

    def __init__(self):
        self._cache: dict[str, str | None] = {}
        self._lock = threading.Lock()
        self._db_loaded = False

    # ── Public API ───────────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> str:
        """Get a secret.  Checks memory cache → DB → os.environ."""
        with self._lock:
            if key in self._cache:
                val = self._cache[key]
                return val if val is not None else default

        # Try DB (synchronous, uses a throwaway connection)
        value = self._get_from_db(key)
        if value:
            with self._lock:
                self._cache[key] = value
            return value

        # Fallback to environment variable
        env_val = os.environ.get(key, "")
        if env_val:
            with self._lock:
                self._cache[key] = env_val
            return env_val

        return default

    def invalidate(self, key: str | None = None):
        """Clear cache.  Pass a key to clear one, or None to clear all."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
                self._db_loaded = False

    def is_setup_complete(self) -> bool:
        """Check if any secrets have been configured in the DB."""
        try:
            import sqlalchemy
            sync_url = DATABASE_URL.replace("+asyncpg", "")
            engine = sqlalchemy.create_engine(sync_url)
            with engine.connect() as conn:
                row = conn.execute(sqlalchemy.text(
                    "SELECT COUNT(*) AS cnt FROM secrets WHERE is_configured = TRUE"
                )).fetchone()
                return (row.cnt or 0) > 0
        except Exception:
            return False

    # ── Convenience properties for boot-time vars ────────────────────────

    @property
    def DATABASE_URL(self) -> str:
        return DATABASE_URL

    @property
    def POSTGRES_PASSWORD(self) -> str:
        return POSTGRES_PASSWORD

    @property
    def ENCRYPTION_KEY(self) -> str:
        return ENCRYPTION_KEY

    @property
    def DASHBOARD_USER(self) -> str:
        return DASHBOARD_USER

    @property
    def DASHBOARD_PASSWORD(self) -> str:
        return DASHBOARD_PASSWORD

    @property
    def DAILY_BUDGET_LIMIT_USD(self) -> float:
        return DAILY_BUDGET_LIMIT_USD

    @property
    def AGENT_DEFAULT_DAILY_LIMIT_USD(self) -> float:
        return AGENT_DEFAULT_DAILY_LIMIT_USD

    @property
    def SLACK_WEBHOOK_URL(self) -> str:
        return self.get("SLACK_WEBHOOK_URL")

    # ── Private ──────────────────────────────────────────────────────────

    def _get_from_db(self, key: str) -> str | None:
        """Query the secrets table and decrypt the value."""
        try:
            import sqlalchemy
            from src.crypto import decrypt

            sync_url = DATABASE_URL.replace("+asyncpg", "")
            engine = sqlalchemy.create_engine(sync_url)
            with engine.connect() as conn:
                row = conn.execute(
                    sqlalchemy.text(
                        "SELECT value_encrypted FROM secrets "
                        "WHERE key = :key AND is_configured = TRUE"
                    ),
                    {"key": key},
                ).fetchone()
                if row and row.value_encrypted:
                    return decrypt(row.value_encrypted)
        except Exception as exc:
            # DB not ready yet (first boot) or table doesn't exist
            logger.debug("secrets_db_read_failed", key=key, error=str(exc))
        return None

    # ── Backwards compatibility: attribute access falls through to get() ─

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)


settings = Settings()

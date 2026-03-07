from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://factory:changeme@localhost:5432/factory"

    # ── Hatchet ──
    HATCHET_CLIENT_TOKEN: str = ""
    HATCHET_CLIENT_TLS_STRATEGY: str = "none"

    # ── Anthropic ──
    ANTHROPIC_API_KEY: str = ""

    # ── Stripe ──
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── Domain & Infra ──
    NAMECHEAP_API_KEY: str = ""
    NAMECHEAP_API_USER: str = ""
    CLOUDFLARE_API_TOKEN: str = ""
    VERCEL_TOKEN: str = ""
    GITHUB_TOKEN: str = ""

    # ── Supabase ──
    SUPABASE_ACCESS_TOKEN: str = ""

    # ── Email ──
    SENDGRID_API_KEY: str = ""
    INSTANTLY_API_KEY: str = ""
    RESEND_API_KEY: str = ""

    # ── Advertising ──
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    META_ADS_ACCESS_TOKEN: str = ""

    # ── Social ──
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""

    # ── Voice / Telephony ──
    RETELL_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # ── Lead Enrichment ──
    APOLLO_API_KEY: str = ""
    HUNTER_API_KEY: str = ""
    DROPCONTACT_API_KEY: str = ""
    ZEROBOUNCE_API_KEY: str = ""
    SPARKTORO_API_KEY: str = ""
    SERPER_API_KEY: str = ""

    # ── Notifications ──
    SLACK_WEBHOOK_URL: str = ""

    # ── Analytics ──
    PLAUSIBLE_BASE_URL: str = "http://localhost:8000"
    PLAUSIBLE_SECRET: str = ""

    # ── Dashboard ──
    DASHBOARD_USER: str = "admin"
    DASHBOARD_PASSWORD: str = "factory"

    # ── Budget Limits (USD) ──
    DAILY_BUDGET_LIMIT_USD: float = Field(default=50.0)
    AGENT_DEFAULT_DAILY_LIMIT_USD: float = Field(default=5.0)

    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL (for alembic, scripts, etc.)."""
        return self.DATABASE_URL.replace("+asyncpg", "")


settings = Settings()

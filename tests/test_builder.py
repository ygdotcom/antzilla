"""Tests for the Builder agent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.builder import (
    Builder,
    _parse_json_response,
    inject_rls_for_missing_tables,
    verify_rls_compliance,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return Builder()


@pytest.fixture
def compliant_sql():
    return """
    CREATE TABLE projects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES auth.users NOT NULL,
        title TEXT NOT NULL
    );
    ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "projects_user" ON projects FOR ALL USING (auth.uid() = user_id);

    CREATE TABLE invoices (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES auth.users NOT NULL,
        amount NUMERIC
    );
    ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "invoices_user" ON invoices FOR ALL USING (auth.uid() = user_id);
    """


@pytest.fixture
def non_compliant_sql():
    return """
    CREATE TABLE projects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES auth.users NOT NULL,
        title TEXT NOT NULL
    );
    ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "projects_user" ON projects FOR ALL USING (auth.uid() = user_id);

    CREATE TABLE invoices (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES auth.users NOT NULL,
        amount NUMERIC
    );
    -- oops, forgot RLS here

    CREATE TABLE line_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        invoice_id UUID REFERENCES invoices NOT NULL,
        description TEXT
    );
    -- oops, forgot RLS here too
    """


@pytest.fixture
def sample_architecture():
    return {
        "app_name": "Quote OS",
        "description": "Professional quoting for Quebec contractors",
        "pages": [
            {"route": "/dashboard", "purpose": "Main workspace", "key_components": ["QuoteList", "OnboardingChecklist"]},
            {"route": "/quotes/new", "purpose": "Create new quote", "key_components": ["QuoteEditor"]},
        ],
        "database_tables": [
            {"name": "quotes", "columns": ["id", "user_id", "client_name", "total"], "rls_policy": "user_id = auth.uid()"},
        ],
        "api_routes": [
            {"route": "/api/quotes", "method": "POST", "purpose": "Create quote"},
        ],
        "integrations": ["stripe", "supabase"],
        "sample_data": {"description": "Sample roofing quote for a residential project"},
        "domain_logic": ["Quebec winter surcharges", "Net 45 payment terms"],
        "data_flywheel": "Aggregate anonymous quote data to improve AI estimates",
        "ecosystem_integration": {"platform": "QuickBooks", "type": "export", "description": "Export quotes as QuickBooks invoices"},
    }


@pytest.fixture
def sample_code_output():
    return {
        "files": [
            {
                "path": "src/app/[locale]/dashboard/page.tsx",
                "content": "export default function Dashboard() { return <div>Dashboard</div> }",
                "action": "replace",
            }
        ],
        "migrations": [
            {
                "filename": "002_quotes.sql",
                "content": (
                    "CREATE TABLE quotes (id UUID PRIMARY KEY, user_id UUID NOT NULL, total NUMERIC);\n"
                    "ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;\n"
                    "CREATE POLICY quotes_user ON quotes FOR ALL USING (auth.uid() = user_id);"
                ),
            }
        ],
        "env_vars": {"NEXT_PUBLIC_APP_NAME": "Quote OS"},
        "messages_fr": {"dashboard": {"title": "Tableau de bord"}},
        "messages_en": {"dashboard": {"title": "Dashboard"}},
    }


# ── RLS Verification Tests (§12 — NON-NEGOTIABLE) ────────────────────────────


class TestRLSVerification:
    """SPEC §12: Every CREATE TABLE MUST have ALTER TABLE ... ENABLE ROW LEVEL SECURITY."""

    def test_compliant_sql_passes(self, compliant_sql):
        result = verify_rls_compliance(compliant_sql)
        assert result["compliant"] is True
        assert len(result["missing_rls"]) == 0
        assert len(result["violations"]) == 0

    def test_non_compliant_sql_detected(self, non_compliant_sql):
        result = verify_rls_compliance(non_compliant_sql)
        assert result["compliant"] is False
        assert "invoices" in result["missing_rls"]
        assert "line_items" in result["missing_rls"]
        assert len(result["violations"]) == 2

    def test_violation_message_references_spec(self, non_compliant_sql):
        result = verify_rls_compliance(non_compliant_sql)
        for v in result["violations"]:
            assert "§12" in v

    def test_empty_sql_is_compliant(self):
        result = verify_rls_compliance("")
        assert result["compliant"] is True

    def test_case_insensitive(self):
        sql = """
        create table MyTable (id int);
        alter table mytable enable row level security;
        """
        result = verify_rls_compliance(sql)
        assert result["compliant"] is True

    def test_create_table_if_not_exists(self):
        sql = """
        CREATE TABLE IF NOT EXISTS profiles (id uuid);
        ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
        """
        result = verify_rls_compliance(sql)
        assert result["compliant"] is True
        assert "profiles" in result["tables_created"]


class TestRLSAutoFix:
    def test_injects_rls_for_missing_tables(self, non_compliant_sql):
        fixed = inject_rls_for_missing_tables(non_compliant_sql, ["invoices", "line_items"])
        result = verify_rls_compliance(fixed)
        assert result["compliant"] is True
        assert "invoices" not in result["missing_rls"]
        assert "line_items" not in result["missing_rls"]

    def test_auto_injected_comment_present(self, non_compliant_sql):
        fixed = inject_rls_for_missing_tables(non_compliant_sql, ["invoices"])
        assert "AUTO-INJECTED RLS" in fixed

    def test_creates_policy_for_each_table(self, non_compliant_sql):
        fixed = inject_rls_for_missing_tables(non_compliant_sql, ["invoices"])
        assert "CREATE POLICY" in fixed
        assert "invoices" in fixed


class TestTemplateRLSCompliance:
    """Verify the actual template-repo migration has RLS on every table."""

    def test_template_migration_has_rls(self):
        migration_path = Path(__file__).resolve().parent.parent / "template-repo" / "supabase" / "migrations" / "001_init.sql"
        if not migration_path.exists():
            pytest.skip("Template migration not found")
        sql = migration_path.read_text()
        result = verify_rls_compliance(sql)
        assert result["compliant"] is True, (
            f"Template migration has tables without RLS: {result['missing_rls']}"
        )


# ── JSON Parser Tests ─────────────────────────────────────────────────────────


class TestParseJSON:
    def test_valid_json(self, sample_architecture):
        parsed = _parse_json_response(json.dumps(sample_architecture))
        assert parsed is not None
        assert parsed["app_name"] == "Quote OS"

    def test_code_fenced(self, sample_architecture):
        text = f"```json\n{json.dumps(sample_architecture)}\n```"
        parsed = _parse_json_response(text)
        assert parsed is not None

    def test_preamble(self, sample_architecture):
        text = f"Here is the architecture:\n\n{json.dumps(sample_architecture)}"
        parsed = _parse_json_response(text)
        assert parsed is not None

    def test_invalid_returns_none(self):
        assert _parse_json_response("not json") is None

    def test_empty_returns_none(self):
        assert _parse_json_response("") is None


# ── Agent Config Tests ────────────────────────────────────────────────────────


class TestBuilderConfig:
    def test_agent_name(self, agent):
        assert agent.agent_name == "builder"

    def test_default_model(self, agent):
        assert agent.default_model == "sonnet"


# ── Step Tests ────────────────────────────────────────────────────────────────


class TestGenerateArchitecture:
    @pytest.mark.asyncio
    async def test_calls_opus(self, agent, sample_architecture):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1,
            "niche": "construction quoting",
            "scout_report": "# Scout Report\nTest",
            "brand_kit": {"colors": {"primary": "#1B4D72"}},
            "gtm_playbook": {},
        })

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.builder.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = (json.dumps(sample_architecture), 0.15)
            result = await agent.generate_architecture(ctx)

        assert result["architecture"]["app_name"] == "Quote OS"
        # Should upgrade to opus for architecture
        mock_claude.assert_called_once()
        call_kwargs = mock_claude.call_args[1]
        assert call_kwargs["model_tier"] == "opus"


class TestGenerateCode:
    @pytest.mark.asyncio
    async def test_returns_files_and_migrations(self, agent, sample_code_output):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1,
            "niche": "test",
            "brand_kit": {},
        })
        ctx.step_output = MagicMock(return_value={"architecture": {"app_name": "Test"}})

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.builder.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = (json.dumps(sample_code_output), 0.05)
            result = await agent.generate_code(ctx)

        code = result["code_output"]
        assert len(code["files"]) == 1
        assert len(code["migrations"]) == 1


class TestVerifyRLS:
    @pytest.mark.asyncio
    async def test_compliant_passes(self, agent, sample_code_output):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"code_output": sample_code_output})

        result = await agent.verify_rls(ctx)
        assert result["rls_compliant"] is True
        assert result["auto_fixed"] is False

    @pytest.mark.asyncio
    async def test_non_compliant_auto_fixed(self, agent):
        bad_output = {
            "files": [],
            "migrations": [{
                "filename": "002_bad.sql",
                "content": "CREATE TABLE bad_table (id int, user_id uuid);",
            }],
        }
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"code_output": bad_output})

        result = await agent.verify_rls(ctx)
        assert result["rls_compliant"] is False
        assert result["auto_fixed"] is True
        assert len(result["violations"]) > 0
        # The fixed migration should now have RLS
        fixed_sql = result["fixed_migrations"][0]["content"]
        assert "ENABLE ROW LEVEL SECURITY" in fixed_sql


class TestFinalize:
    @pytest.mark.asyncio
    async def test_updates_business_status(self, agent):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"business_id": 1})
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "create_github_repo": {"repo": "ygdotcom/test-biz"},
                "push_to_github": {"pushed_files": [{"path": "src/app.tsx", "status": 201}]},
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.builder.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.finalize(ctx)

        assert result["status"] == "building"
        assert result["github_repo"] == "ygdotcom/test-biz"
        assert result["files_pushed"] == 1


class TestArchitecturePrompt:
    """Verify the architecture prompt encodes spec requirements."""

    def test_mentions_empty_dashboard_ban(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "vide" in ARCHITECTURE_PROMPT.lower() or "empty" in ARCHITECTURE_PROMPT.lower()

    def test_mentions_reverse_trial(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "14" in ARCHITECTURE_PROMPT
        assert "trial" in ARCHITECTURE_PROMPT.lower() or "essai" in ARCHITECTURE_PROMPT.lower()

    def test_mentions_rls(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "RLS" in ARCHITECTURE_PROMPT

    def test_mentions_bilingual(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "FR/EN" in ARCHITECTURE_PROMPT or "bilingual" in ARCHITECTURE_PROMPT.lower() or "bilingue" in ARCHITECTURE_PROMPT.lower()

    def test_mentions_charm_pricing(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "$49" in ARCHITECTURE_PROMPT

    def test_mentions_3_fields_max(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "3 champs" in ARCHITECTURE_PROMPT or "3 fields" in ARCHITECTURE_PROMPT.lower()

    def test_mentions_data_flywheel(self):
        from src.agents.builder import CODE_GEN_PROMPT
        # Data flywheel is part of the architecture prompt
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "flywheel" in ARCHITECTURE_PROMPT.lower() or "agreg" in ARCHITECTURE_PROMPT.lower()


class TestOnboardingRequirements:
    """SPEC §5: Never show an empty dashboard."""

    def test_architecture_prompt_requires_sample_data(self):
        from src.agents.builder import ARCHITECTURE_PROMPT
        assert "pré-peupler" in ARCHITECTURE_PROMPT.lower() or "pre-populate" in ARCHITECTURE_PROMPT.lower()

    def test_code_gen_prompt_requires_sample_data(self):
        from src.agents.builder import CODE_GEN_PROMPT
        assert "pré-peuplé" in CODE_GEN_PROMPT.lower() or "pre-populate" in CODE_GEN_PROMPT.lower()

    def test_code_gen_requires_onboarding_checklist(self):
        from src.agents.builder import CODE_GEN_PROMPT
        assert "OnboardingChecklist" in CODE_GEN_PROMPT

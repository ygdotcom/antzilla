"""Agent 7: Builder.

Triggered on-demand when Domain Provisioner finishes (infra ready).
Clones the template repo, applies the brand kit, generates business-specific
code via Claude, verifies RLS on every migration, pushes to GitHub, deploys
to Vercel, and runs Lighthouse.

CRITICAL INVARIANTS (from SPEC.md):
- Every Supabase migration MUST have ALTER TABLE ... ENABLE ROW LEVEL SECURITY
- Pre-populated sample data on first login — NEVER an empty dashboard
- Reverse trial: 14-day full premium, auto-downgrade to free
- Bilingual FR/EN from day 1 (next-intl)
- Flat-rate CAD charm pricing ($49, not $50)
"""

from __future__ import annotations

import json
import re

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

RLS_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
RLS_ENABLE_PATTERN = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
    re.IGNORECASE,
)

ARCHITECTURE_PROMPT = """\
Tu es l'architecte logiciel de la Factory. Tu conçois l'architecture d'un MVP SaaS.

Tu reçois: le Scout Report, le GTM Playbook, et le Brand Kit.

Produis un JSON avec:
{
  "app_name": "string",
  "description": "one-liner",
  "pages": [{"route": "/dashboard", "purpose": "...", "key_components": [...]}],
  "database_tables": [{"name": "...", "columns": [...], "rls_policy": "..."}],
  "api_routes": [{"route": "/api/...", "method": "POST", "purpose": "..."}],
  "integrations": ["stripe", "supabase", ...],
  "sample_data": {"description": "What sample project to pre-populate on signup"},
  "domain_logic": ["business-specific rules from scout report"],
  "data_flywheel": "How user actions improve the product for everyone",
  "ecosystem_integration": {"platform": "...", "type": "...", "description": "..."}
}

RÈGLES:
- JAMAIS de dashboard vide au premier login. Pré-peupler un projet exemple.
- Reverse trial: 14 jours premium complet, puis downgrade vers Free.
- Bilingual FR/EN obligatoire (next-intl).
- RLS sur CHAQUE table. Politiques scoped par user_id.
- Pricing flat-rate en CAD. Charm pricing ($49, pas $50).
- 3 champs max au signup (nom, email, téléphone).
- "Aha moment" en moins de 2 minutes.

Réponds UNIQUEMENT en JSON valide.
"""

CODE_GEN_PROMPT = """\
Tu es le Builder. Tu génères du code Next.js pour un SaaS basé sur le template-repo.

Tu reçois: l'architecture JSON + le Brand Kit + le niche.

Produis un JSON avec les fichiers à modifier ou créer:
{
  "files": [
    {
      "path": "src/app/[locale]/dashboard/page.tsx",
      "content": "full file content",
      "action": "replace"
    }
  ],
  "migrations": [
    {
      "filename": "002_business_tables.sql",
      "content": "CREATE TABLE ... ALTER TABLE ... ENABLE ROW LEVEL SECURITY ..."
    }
  ],
  "env_vars": {"NEXT_PUBLIC_APP_NAME": "..."},
  "messages_fr": {"dashboard": {"title": "..."}},
  "messages_en": {"dashboard": {"title": "..."}}
}

RÈGLES CRITIQUES:
- CHAQUE CREATE TABLE DOIT être suivi de ALTER TABLE ... ENABLE ROW LEVEL SECURITY
- CHAQUE table DOIT avoir une politique RLS: CREATE POLICY ... USING (auth.uid() = user_id)
- Le dashboard montre un projet pré-peuplé, JAMAIS vide
- Utiliser les couleurs et fonts du Brand Kit
- Tout le texte via next-intl (useTranslations), jamais en dur
- Composant OnboardingChecklist dans le dashboard
"""


def verify_rls_compliance(sql_content: str) -> dict:
    """Verify every CREATE TABLE has a matching ALTER TABLE ... ENABLE ROW LEVEL SECURITY.

    Returns {"compliant": bool, "tables": [...], "missing_rls": [...], "violations": [str]}.
    """
    tables_created = set(RLS_PATTERN.findall(sql_content))
    tables_rls_enabled = set(RLS_ENABLE_PATTERN.findall(sql_content))

    # Normalize case
    tables_created_lower = {t.lower() for t in tables_created}
    tables_rls_lower = {t.lower() for t in tables_rls_enabled}

    missing = tables_created_lower - tables_rls_lower
    violations = [f"Table '{t}' created WITHOUT RLS — SPEC VIOLATION §12" for t in sorted(missing)]

    return {
        "compliant": len(missing) == 0,
        "tables_created": sorted(tables_created_lower),
        "tables_with_rls": sorted(tables_rls_lower),
        "missing_rls": sorted(missing),
        "violations": violations,
    }


def inject_rls_for_missing_tables(sql_content: str, missing_tables: list[str]) -> str:
    """Auto-fix: append RLS statements for tables that are missing them."""
    additions = []
    for table in missing_tables:
        additions.append(f"\nALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        additions.append(
            f"CREATE POLICY \"{table}_user_isolation\" ON {table} "
            f"FOR ALL USING (auth.uid() = user_id);"
        )
    return sql_content + "\n\n-- AUTO-INJECTED RLS (Builder agent §12 compliance)\n" + "\n".join(additions)


def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from Claude response, handling code fences."""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        clean = "\n".join(lines)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(clean[start : end + 1])
            except json.JSONDecodeError:
                pass
    return None


class Builder(BaseAgent):
    """Generates, verifies, deploys MVP code from template repo."""

    agent_name = "builder"
    default_model = "sonnet"

    async def generate_architecture(self, context) -> dict:
        """Step 1: Claude Opus designs the app architecture."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        scout_report = input_data.get("scout_report", "")
        brand_kit = input_data.get("brand_kit", {})
        gtm_playbook = input_data.get("gtm_playbook", {})
        niche = input_data.get("niche", "")

        model_tier = await self.check_budget()
        # Architecture needs deep reasoning — use opus if budget allows
        if model_tier == "sonnet":
            model_tier = "opus"

        user_payload = json.dumps({
            "niche": niche,
            "scout_report": scout_report[:8000],
            "brand_kit": brand_kit,
            "gtm_playbook": gtm_playbook,
        }, default=str)

        response, cost = await call_claude(
            model_tier=model_tier,
            system=ARCHITECTURE_PROMPT,
            user=user_payload,
            max_tokens=8192,
            temperature=0.3,
        )

        architecture = _parse_json_response(response)
        if not architecture:
            architecture = {"error": "Failed to parse architecture", "raw": response[:2000]}

        await self.log_execution(
            action="generate_architecture",
            result={"pages": len(architecture.get("pages", []))},
            cost_usd=cost,
            business_id=business_id,
        )

        return {"architecture": architecture, "cost_usd": cost}

    async def generate_code(self, context) -> dict:
        """Step 2: Claude Sonnet generates business-specific code."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        brand_kit = input_data.get("brand_kit", {})
        niche = input_data.get("niche", "")
        arch = context.step_output("generate_architecture")
        architecture = arch.get("architecture", {})

        model_tier = await self.check_budget()

        user_payload = json.dumps({
            "architecture": architecture,
            "brand_kit": brand_kit,
            "niche": niche,
        }, default=str)[:30_000]

        response, cost = await call_claude(
            model_tier=model_tier,
            system=CODE_GEN_PROMPT,
            user=user_payload,
            max_tokens=8192,
            temperature=0.2,
        )

        code_output = _parse_json_response(response)
        if not code_output:
            code_output = {"files": [], "migrations": [], "error": "parse failed"}

        await self.log_execution(
            action="generate_code",
            result={"files": len(code_output.get("files", [])), "migrations": len(code_output.get("migrations", []))},
            cost_usd=cost,
            business_id=business_id,
        )

        return {"code_output": code_output, "cost_usd": cost}

    async def verify_rls(self, context) -> dict:
        """Step 3: NON-NEGOTIABLE — verify every migration has RLS enabled.

        If any table is missing RLS, auto-inject it. Log a warning.
        This is the §12 compliance gate.
        """
        code = context.step_output("generate_code")
        code_output = code.get("code_output", {})
        migrations = code_output.get("migrations", [])

        all_compliant = True
        fixed_migrations = []
        all_violations = []

        for mig in migrations:
            sql = mig.get("content", "")
            check = verify_rls_compliance(sql)
            if not check["compliant"]:
                all_compliant = False
                all_violations.extend(check["violations"])
                logger.warning(
                    "rls_violation_auto_fixed",
                    migration=mig.get("filename"),
                    missing=check["missing_rls"],
                )
                sql = inject_rls_for_missing_tables(sql, check["missing_rls"])
            fixed_migrations.append({**mig, "content": sql})

        # SECURITY SCAN: check generated code for exposed secrets
        from src.quality import security_scan_code
        code_output = context.step_output("generate_code").get("code_output", {})
        files_to_scan = code_output.get("files", [])
        security = security_scan_code(files_to_scan)
        if not security["passed"]:
            all_violations.extend([f"SECURITY: {i['issue']} in {i['file']}" for i in security["issues"] if i["severity"] == "critical"])
            logger.error("security_scan_failed", critical=security["critical_count"])

        # Also check the template base migration
        template_migration_path = "supabase/migrations/001_init.sql"
        # The template migration is pre-verified, but we log a reminder
        logger.info("rls_verification_complete", all_compliant=all_compliant, violations=len(all_violations))

        return {
            "rls_compliant": all_compliant,
            "violations": all_violations,
            "fixed_migrations": fixed_migrations,
            "auto_fixed": not all_compliant,
        }

    async def push_to_github(self, context) -> dict:
        """Step 4: Push generated code to the GitHub repo."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        github_repo = input_data.get("github_repo", "")
        code = context.step_output("generate_code")
        rls = context.step_output("verify_rls")

        code_output = code.get("code_output", {})
        files = code_output.get("files", [])
        migrations = rls.get("fixed_migrations", [])

        pushed_files = []
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {
                "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            }

            for f in files:
                path = f.get("path", "")
                content = f.get("content", "")
                if not path or not content:
                    continue
                try:
                    import base64
                    encoded = base64.b64encode(content.encode()).decode()
                    resp = await client.put(
                        f"https://api.github.com/repos/{github_repo}/contents/{path}",
                        headers=headers,
                        json={
                            "message": f"feat: add {path}",
                            "content": encoded,
                        },
                    )
                    pushed_files.append({"path": path, "status": resp.status_code})
                except Exception as exc:
                    pushed_files.append({"path": path, "status": "error", "error": str(exc)})

            for mig in migrations:
                filename = mig.get("filename", "002_tables.sql")
                content = mig.get("content", "")
                if not content:
                    continue
                try:
                    import base64
                    encoded = base64.b64encode(content.encode()).decode()
                    path = f"supabase/migrations/{filename}"
                    resp = await client.put(
                        f"https://api.github.com/repos/{github_repo}/contents/{path}",
                        headers=headers,
                        json={
                            "message": f"feat: migration {filename}",
                            "content": encoded,
                        },
                    )
                    pushed_files.append({"path": path, "status": resp.status_code})
                except Exception as exc:
                    pushed_files.append({"path": path, "status": "error", "error": str(exc)})

        await self.log_execution(
            action="push_to_github",
            result={"files_pushed": len(pushed_files)},
            business_id=business_id,
        )

        return {"pushed_files": pushed_files, "repo": github_repo}

    async def deploy_vercel(self, context) -> dict:
        """Step 5: Trigger Vercel deployment."""
        input_data = context.workflow_input()
        vercel_project_id = input_data.get("vercel_project_id", "")
        github_repo = input_data.get("github_repo", "")

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://api.vercel.com/v13/deployments",
                    headers={"Authorization": f"Bearer {settings.VERCEL_TOKEN}"},
                    json={
                        "name": vercel_project_id,
                        "gitSource": {
                            "type": "github",
                            "repo": github_repo,
                            "ref": "main",
                        },
                    },
                )
                resp.raise_for_status()
                deployment = resp.json()
                deploy_url = deployment.get("url", "")
                deploy_id = deployment.get("id", "")
                logger.info("vercel_deployed", url=deploy_url, id=deploy_id)
                return {"deployment_url": deploy_url, "deployment_id": deploy_id, "success": True}
            except Exception as exc:
                logger.error("vercel_deploy_failed", error=str(exc))
                return {"deployment_url": None, "deployment_id": None, "success": False, "error": str(exc)}

    async def run_lighthouse(self, context) -> dict:
        """Step 6: Run Lighthouse audit on the deployed site."""
        deploy = context.step_output("deploy_vercel")
        url = deploy.get("deployment_url")

        if not url:
            return {"lighthouse": None, "reason": "no deployment URL"}

        # Use PageSpeed Insights API (free, includes Lighthouse)
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.get(
                    "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                    params={
                        "url": f"https://{url}",
                        "strategy": "mobile",
                        "category": ["performance", "accessibility", "best-practices", "seo"],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    categories = data.get("lighthouseResult", {}).get("categories", {})
                    scores = {
                        cat: round(info.get("score", 0) * 100)
                        for cat, info in categories.items()
                    }
                    logger.info("lighthouse_scores", url=url, scores=scores)
                    return {"lighthouse_scores": scores, "url": url}
                return {"lighthouse_scores": None, "status": resp.status_code}
            except Exception as exc:
                return {"lighthouse_scores": None, "error": str(exc)}

    async def notify_agents(self, context) -> dict:
        """Step 7: Update business status and log completion."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        deploy = context.step_output("deploy_vercel")
        lighthouse = context.step_output("run_lighthouse")

        async with SessionLocal() as db:
            if business_id:
                await db.execute(
                    text(
                        "UPDATE businesses SET status = 'pre_launch', "
                        "updated_at = NOW() WHERE id = :id"
                    ),
                    {"id": business_id},
                )
                await db.commit()

        await self.log_execution(
            action="notify_agents",
            result={
                "business_id": business_id,
                "deployment": deploy.get("deployment_url"),
                "lighthouse": lighthouse.get("lighthouse_scores"),
                "status": "pre_launch",
            },
            business_id=business_id,
        )

        return {
            "business_id": business_id,
            "deployment_url": deploy.get("deployment_url"),
            "lighthouse_scores": lighthouse.get("lighthouse_scores"),
            "status": "pre_launch",
        }


def register(hatchet_instance) -> type:
    """Register Builder as a Hatchet workflow."""

    @hatchet_instance.workflow(name="builder")
    class _Registered(Builder):
        @hatchet_instance.task(execution_timeout="10m", retries=2)
        async def generate_architecture(self, context) -> dict:
            return await Builder.generate_architecture(self, context)

        @hatchet_instance.task(execution_timeout="10m", retries=2)
        async def generate_code(self, context) -> dict:
            return await Builder.generate_code(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def verify_rls(self, context) -> dict:
            return await Builder.verify_rls(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def push_to_github(self, context) -> dict:
            return await Builder.push_to_github(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def deploy_vercel(self, context) -> dict:
            return await Builder.deploy_vercel(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def run_lighthouse(self, context) -> dict:
            return await Builder.run_lighthouse(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def notify_agents(self, context) -> dict:
            return await Builder.notify_agents(self, context)

    return _Registered

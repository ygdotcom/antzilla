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
You are the VP of Product at Stripe, designing a vertical SaaS MVP.
The product must feel premium and trustworthy from the first click.

You receive: Scout Report, GTM Playbook, Brand Kit.

Design an architecture that a customer would happily pay $49/month for.
Think: what is the ONE core action this user does daily? Design everything around that.

Produce JSON:
{
  "app_name": "string",
  "description": "one-liner value prop addressing the ICP's #1 pain",
  "headline_fr": "Compelling French headline for landing page hero",
  "headline_en": "Compelling English headline for landing page hero",
  "subtitle_fr": "Supporting subtitle in French",
  "subtitle_en": "Supporting subtitle in English",
  "features": [
    {"name_en": "...", "name_fr": "...", "desc_en": "...", "desc_fr": "...", "icon": "lucide-react icon name"}
  ],
  "how_it_works": [
    {"step": 1, "title_en": "...", "title_fr": "...", "desc_en": "...", "desc_fr": "..."}
  ],
  "pages": [{"route": "/dashboard", "purpose": "...", "key_components": [...]}],
  "database_tables": [{"name": "...", "columns": [...], "rls_policy": "..."}],
  "api_routes": [{"route": "/api/...", "method": "POST", "purpose": "..."}],
  "sample_data": {"description": "Realistic sample data pre-populated on first login"},
  "pricing": {
    "free": {"name": "Gratuit", "price": 0, "features": ["..."]},
    "pro": {"name": "Pro", "price": 49, "features": ["..."]},
    "business": {"name": "Affaires", "price": 99, "features": ["..."]}
  }
}

RULES:
- NEVER empty dashboard. Pre-populate with realistic sample data.
- Reverse trial: 14 days full premium, then downgrade to Free.
- Bilingual FR/EN (next-intl). All text must exist in both languages.
- RLS on EVERY table, scoped by user_id.
- CAD charm pricing ($49, not $50).
- 3 fields max at signup (name, email, phone).
- "Aha moment" in under 2 minutes.
- Features should use lucide-react icon names (Receipt, FileText, BarChart3, etc.)

Respond ONLY with valid JSON.
"""

CODE_GEN_PROMPT = """\
You are the head of design at Stripe. You're building a vertical SaaS product.
Your design must be so polished that customers trust it instantly and want to pay.

You receive: architecture JSON + brand kit + niche.

DESIGN PRINCIPLES (Stripe-level):
- Generous whitespace, 8px grid, consistent spacing
- Subtle gradients, soft shadows (shadow-sm, shadow-lg with brand color/25 opacity)
- Micro-interactions: hover transitions, group-hover effects
- Typography hierarchy: one bold headline, lighter subheads, muted body text
- Icons from lucide-react to add visual interest (never raw text bullets)
- Color: use brand kit primary for CTAs and accents, keep backgrounds clean
- Cards with rounded-2xl, subtle borders, hover elevation
- Professional touches: backdrop-blur nav, radial gradient backgrounds, pill badges

BRAND KIT APPLICATION:
The template uses CSS variables in globals.css. You MUST generate a brand.css file that
overrides these variables with the brand kit colors:

Example brand.css:
:root {
  --color-primary: #2E5266;
  --color-primary-50: #f0f5f7;
  --color-primary-500: #2E5266;
  --color-primary-600: #253f4f;
  --color-accent: #52AB98;
  --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-heading: 'Cabinet Grotesk', system-ui, sans-serif;
}

Include Google Fonts link in a <Head> component if using custom fonts.

PACKAGES AVAILABLE (already in package.json — DO NOT import others):
- next, react, react-dom, next-intl
- @supabase/supabase-js, @supabase/ssr
- stripe, @stripe/stripe-js
- lucide-react (icons — use extensively for visual polish)
- recharts (charts for dashboards)
- clsx, tailwind-merge (via @/lib/utils → cn())

UI COMPONENTS AVAILABLE:
- @/components/ui/card → Card, CardHeader, CardTitle, CardDescription, CardContent
- @/components/ui/button → Button (variants: default, outline, ghost)
- @/components/ui/badge → Badge
- @/components/ui/input → Input
- @/lib/utils → cn()

DO NOT REPLACE THESE TEMPLATE FILES:
- src/app/[locale]/layout.tsx, src/app/globals.css
- src/middleware.ts, src/i18n/*, src/lib/supabase/*, src/lib/stripe.ts
- next.config.ts, tailwind.config.ts, tsconfig.json, package.json

YOU SHOULD REPLACE:
- src/app/[locale]/page.tsx (landing page — make it stunning with real copy for the niche)
- src/app/[locale]/dashboard/page.tsx (main dashboard — pre-populated, never empty)
- src/app/[locale]/pricing/page.tsx (3-tier pricing with charm pricing in CAD)

YOU SHOULD CREATE:
- src/app/brand.css (CSS variable overrides from brand kit — imported by page.tsx)
- Business-specific pages with REAL functionality
- Business-specific components with REAL Supabase CRUD
- Supabase migration: 002_business_tables.sql with business-specific tables

SUPABASE IS PRE-CONFIGURED. Use these imports:
- Client components: import { createClient } from '@/lib/supabase/client'
- Server components: import { createClient } from '@/lib/supabase/server'
- The DB already has: profiles, projects, subscriptions, referrals tables
- Auth is already set up — use supabase.auth.getUser() to check login

THE APP MUST BE A REAL WORKING PRODUCT, NOT A MARKETING SITE.

LANDING PAGE:
- Hero with compelling headline addressing the ICP's #1 pain
- 3 feature cards with lucide-react icons
- "How it works" 3-step section
- Pricing preview (3 tiers: Free $0, Pro $49, Business $99 CAD)
- CTA with trust signals

DASHBOARD (the actual product — THIS IS THE CORE):
- Server component that fetches real data from Supabase
- Pre-populated with sample data on first login (the trigger in 001_init.sql handles this)
- Stats cards showing real metrics (count from DB)
- Data table or card grid showing the core business entities
- CREATE form/modal to add new items (use Server Actions or client-side Supabase)
- EDIT and DELETE functionality on each item
- All mutations go through Supabase client

BUSINESS-SPECIFIC CRUD (REQUIRED):
- Identify the ONE core entity for this business (e.g., receipts, contracts, invoices)
- Create a migration 002_business_tables.sql with the table for this entity
  - Must have: id UUID, user_id UUID REFERENCES auth.users, + business fields
  - Must have: ALTER TABLE ... ENABLE ROW LEVEL SECURITY
  - Must have: CREATE POLICY ... USING (auth.uid() = user_id)
- Create a dashboard page that lists these entities
- Create a form to add/edit them
- Create Server Actions or API routes for mutations
- Example for a receipt tracker:
  - Table: receipts (id, user_id, vendor, amount, tax_type, category, receipt_date, created_at)
  - Dashboard: list receipts, filter by category, show totals
  - Form: add receipt with vendor, amount, tax type (GST/HST/PST), category
  - Stats: total expenses, tax breakdown, monthly trend

SERVER ACTIONS PATTERN (use this for mutations):
'use server'
import { createClient } from '@/lib/supabase/server'
import { revalidatePath } from 'next/cache'

export async function createItem(formData: FormData) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error('Not authenticated')
  await supabase.from('items').insert({
    user_id: user.id,
    name: formData.get('name'),
    // ... other fields
  })
  revalidatePath('/dashboard')
}

OUTPUT FORMAT — respond ONLY with valid JSON:
{
  "files": [
    {"path": "src/app/brand.css", "content": ":root { --color-primary: ... }", "action": "create"},
    {"path": "src/app/[locale]/page.tsx", "content": "...", "action": "replace"},
    {"path": "messages/en.json", "content": "{...}", "action": "replace"},
    {"path": "messages/fr.json", "content": "{...}", "action": "replace"}
  ],
  "migrations": [
    {"filename": "002_business_tables.sql", "content": "CREATE TABLE ... ALTER TABLE ... ENABLE ROW LEVEL SECURITY ..."}
  ]
}

CRITICAL RULES:
- Every CREATE TABLE MUST have ALTER TABLE ... ENABLE ROW LEVEL SECURITY
- Every table MUST have a RLS policy: CREATE POLICY ... USING (auth.uid() = user_id)
- Dashboard shows pre-populated sample data, NEVER empty
- All text via next-intl (useTranslations), never hardcoded
- Bilingual FR/EN — the Copywriter agent has already generated complete messages/fr.json
  and messages/en.json. Use the translation keys from those files in your components.
  Example: const t = useTranslations(); then t('hero.title'), t('features.f1_title'), etc.
- DO NOT include messages/*.json in your output — they're handled separately
- CAD charm pricing ($49, not $50)
- NO import of './globals.css' — it's already in layout.tsx
- Respond ONLY with valid JSON. No text before or after.
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
    """Parse JSON from Claude response, handling code fences and truncation."""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        clean = "\n".join(lines)

    # Try direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            pass

    # If JSON is truncated (hit token limit), try to repair it
    if start >= 0:
        fragment = clean[start:]
        # Close all open strings, arrays, objects
        open_braces = fragment.count("{") - fragment.count("}")
        open_brackets = fragment.count("[") - fragment.count("]")
        # Check if we're inside a string (odd number of unescaped quotes)
        in_string = fragment.count('"') % 2 == 1
        repair = fragment
        if in_string:
            repair += '"'
        repair += "]" * max(0, open_brackets)
        repair += "}" * max(0, open_braces)
        try:
            return json.loads(repair)
        except json.JSONDecodeError:
            pass

    return None


class Builder(BaseAgent):
    """Generates, verifies, deploys MVP code from template repo."""

    agent_name = "builder"
    default_model = "sonnet"

    @staticmethod
    def _flatten_keys(obj: dict, prefix: str = "") -> list[str]:
        """Flatten nested dict keys to dot notation: {'a': {'b': 1}} → ['a.b']."""
        keys = []
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(Builder._flatten_keys(v, full_key))
            else:
                keys.append(full_key)
        return keys

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
        messages_fr = input_data.get("messages_fr", {})
        arch = context.step_output("generate_architecture")
        architecture = arch.get("architecture", {})

        model_tier = await self.check_budget()

        # Include the translation keys so Claude uses them in components
        available_keys = list(self._flatten_keys(messages_fr)) if messages_fr else []

        user_payload = json.dumps({
            "architecture": architecture,
            "brand_kit": brand_kit,
            "niche": niche,
            "translation_keys_available": available_keys[:200],
        }, default=str)[:30_000]

        response, cost = await call_claude(
            model_tier=model_tier,
            system=CODE_GEN_PROMPT,
            user=user_payload,
            max_tokens=32768,
            temperature=0.2,
        )

        code_output = _parse_json_response(response)
        if not code_output or not code_output.get("files"):
            # Claude sometimes returns code blocks instead of pure JSON.
            # Try extracting individual file blocks as a fallback.
            logger.warning("code_gen_json_parse_failed", response_len=len(response))
            files = []
            # Look for ```filename patterns
            import re
            file_blocks = re.findall(
                r'(?:^|\n)(?:###?\s*)?`?([^\n`]+\.[a-z]{1,4})`?\s*\n```[a-z]*\n(.*?)```',
                response, re.DOTALL,
            )
            for path, content in file_blocks:
                path = path.strip().strip("`").strip()
                if path and content.strip():
                    files.append({"path": path, "content": content.strip(), "action": "replace"})
            if files:
                code_output = {"files": files, "migrations": [], "recovered": True}
                logger.info("code_gen_recovered", files=len(files))
            else:
                code_output = {"files": [], "migrations": [], "error": "parse failed", "raw_preview": response[:500]}

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

    async def create_github_repo(self, context) -> dict:
        """Step 4: Create a GitHub repo from the template if one doesn't exist."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        github_repo = input_data.get("github_repo", "")

        token = settings.get("GITHUB_TOKEN")
        if not token:
            logger.warning("github_token_missing")
            return {"repo": "", "created": False, "error": "GITHUB_TOKEN not configured"}

        # If a repo was provided (by Domain Provisioner), use it
        if github_repo:
            return {"repo": github_repo, "created": False}

        # Derive repo name from business
        async with SessionLocal() as db:
            biz = (await db.execute(
                text("SELECT slug FROM businesses WHERE id = :id"), {"id": business_id}
            )).fetchone() if business_id else None
        repo_name = biz.slug if biz else f"factory-biz-{business_id}"

        github_org = settings.get("GITHUB_ORG", "ygdotcom")
        full_name = f"{github_org}/{repo_name}"

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
            # Check if repo already exists
            check = await client.get(
                f"https://api.github.com/repos/{full_name}", headers=headers
            )
            if check.status_code == 200:
                logger.info("github_repo_exists", repo=full_name)
                if business_id:
                    async with SessionLocal() as db:
                        await db.execute(text(
                            "UPDATE businesses SET github_repo = :repo, updated_at = NOW() WHERE id = :id"
                        ), {"repo": full_name, "id": business_id})
                        await db.commit()
                return {"repo": full_name, "created": False}

            # Create repo
            resp = await client.post(
                f"https://api.github.com/orgs/{github_org}/repos",
                headers=headers,
                json={
                    "name": repo_name,
                    "description": f"Antzilla-built SaaS: {repo_name}",
                    "private": True,
                    "auto_init": True,
                },
            )
            if resp.status_code == 404:
                # Org doesn't exist — create under personal account
                resp = await client.post(
                    "https://api.github.com/user/repos",
                    headers=headers,
                    json={
                        "name": repo_name,
                        "description": f"Antzilla-built SaaS: {repo_name}",
                        "private": True,
                        "auto_init": True,
                    },
                )
            if resp.status_code in (201, 200):
                created_repo = resp.json()
                full_name = created_repo.get("full_name", full_name)
                logger.info("github_repo_created", repo=full_name)
            else:
                logger.error("github_repo_create_failed", status=resp.status_code, body=resp.text[:300])
                return {"repo": "", "created": False, "error": f"GitHub API {resp.status_code}"}

        if business_id:
            async with SessionLocal() as db:
                await db.execute(text(
                    "UPDATE businesses SET github_repo = :repo, updated_at = NOW() WHERE id = :id"
                ), {"repo": full_name, "id": business_id})
                await db.commit()

        await self.log_execution(
            action="create_github_repo",
            result={"repo": full_name},
            business_id=business_id,
        )
        return {"repo": full_name, "created": True}

    async def _batch_commit(self, github_repo: str, files: list[dict], message: str) -> dict:
        """Push multiple files in a single Git commit using the Trees API."""
        import base64

        token = settings.get("GITHUB_TOKEN")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

        async with httpx.AsyncClient(timeout=60) as client:
            # Get the latest commit SHA (HEAD of main)
            ref_resp = await client.get(
                f"https://api.github.com/repos/{github_repo}/git/ref/heads/main", headers=headers
            )
            if ref_resp.status_code != 200:
                return {"success": False, "error": f"get ref: {ref_resp.status_code}"}
            head_sha = ref_resp.json()["object"]["sha"]

            # Get the tree SHA of HEAD
            commit_resp = await client.get(
                f"https://api.github.com/repos/{github_repo}/git/commits/{head_sha}", headers=headers
            )
            base_tree_sha = commit_resp.json()["tree"]["sha"]

            # Create blobs for each file
            tree_items = []
            for f in files:
                blob_resp = await client.post(
                    f"https://api.github.com/repos/{github_repo}/git/blobs",
                    headers=headers,
                    json={"content": f["content"], "encoding": "utf-8"},
                )
                if blob_resp.status_code != 201:
                    logger.warning("blob_create_failed", path=f["path"], status=blob_resp.status_code)
                    continue
                tree_items.append({
                    "path": f["path"],
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_resp.json()["sha"],
                })

            if not tree_items:
                return {"success": False, "error": "no blobs created"}

            # Create a new tree
            tree_resp = await client.post(
                f"https://api.github.com/repos/{github_repo}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_items},
            )
            if tree_resp.status_code != 201:
                return {"success": False, "error": f"create tree: {tree_resp.status_code}"}

            # Create a commit
            new_commit_resp = await client.post(
                f"https://api.github.com/repos/{github_repo}/git/commits",
                headers=headers,
                json={
                    "message": message,
                    "tree": tree_resp.json()["sha"],
                    "parents": [head_sha],
                },
            )
            if new_commit_resp.status_code != 201:
                return {"success": False, "error": f"create commit: {new_commit_resp.status_code}"}

            # Update the reference to point to the new commit
            update_resp = await client.patch(
                f"https://api.github.com/repos/{github_repo}/git/refs/heads/main",
                headers=headers,
                json={"sha": new_commit_resp.json()["sha"]},
            )
            if update_resp.status_code != 200:
                return {"success": False, "error": f"update ref: {update_resp.status_code}"}

        return {"success": True, "files": len(tree_items), "sha": new_commit_resp.json()["sha"]}

    async def push_template(self, context) -> dict:
        """Step 5: Push the entire template-repo as a single commit."""
        from pathlib import Path

        repo_info = context.step_output("create_github_repo")
        github_repo = repo_info.get("repo", "")
        if not github_repo:
            return {"pushed": 0, "error": "No repo"}

        template_dir = Path(__file__).resolve().parent.parent.parent / "template-repo"
        if not template_dir.exists():
            logger.warning("template_repo_missing", path=str(template_dir))
            return {"pushed": 0, "error": "template-repo/ not found"}

        skip = {"node_modules", ".next", "package-lock.json", "next-env.d.ts", ".DS_Store"}
        files_to_push = []
        for f in sorted(template_dir.rglob("*")):
            if f.is_dir():
                continue
            rel = str(f.relative_to(template_dir))
            if any(s in rel for s in skip):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                files_to_push.append({"path": rel, "content": content})
            except (UnicodeDecodeError, OSError):
                continue

        result = await self._batch_commit(
            github_repo, files_to_push,
            "chore: initialize from factory template-repo"
        )

        input_data = context.workflow_input()
        await self.log_execution(
            action="push_template",
            result={"pushed": result.get("files", 0), "total": len(files_to_push), "repo": github_repo},
            business_id=input_data.get("business_id"),
        )
        logger.info("template_pushed", pushed=result.get("files", 0), total=len(files_to_push), single_commit=True)
        return {"pushed": result.get("files", 0), "total": len(files_to_push)}

    PROTECTED_TEMPLATE_FILES = {
        "src/app/[locale]/layout.tsx",
        "src/app/globals.css",
        "src/middleware.ts",
        "src/i18n/routing.ts",
        "src/i18n/request.ts",
        "src/lib/supabase/client.ts",
        "src/lib/supabase/server.ts",
        "src/lib/stripe.ts",
        "src/lib/referral.ts",
        "src/lib/utils.ts",
        "next.config.ts",
        "tailwind.config.ts",
        "tsconfig.json",
        "postcss.config.mjs",
        "package.json",
        ".gitignore",
        ".env.example",
    }

    async def push_to_github(self, context) -> dict:
        """Step 6: Push Claude-generated code on top of the template (single commit)."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        repo_info = context.step_output("create_github_repo")
        github_repo = repo_info.get("repo", "")
        if not github_repo:
            return {"pushed_files": [], "repo": "", "error": "No repo available"}

        code = context.step_output("generate_code")
        rls = context.step_output("verify_rls")

        code_output = code.get("code_output", {})

        def _is_protected(path: str) -> bool:
            if path in self.PROTECTED_TEMPLATE_FILES:
                return True
            protected_names = {"layout.tsx", "globals.css", "middleware.ts", "next.config.ts",
                               "tailwind.config.ts", "tsconfig.json", "package.json"}
            basename = path.rsplit("/", 1)[-1] if "/" in path else path
            if basename in protected_names:
                logger.info("protected_file_blocked", path=path, basename=basename)
                return True
            return False

        all_files = []
        for f in code_output.get("files", []):
            if f.get("path") and f.get("content") and not _is_protected(f["path"]):
                all_files.append({"path": f["path"], "content": f["content"]})
        for mig in rls.get("fixed_migrations", []):
            if mig.get("content"):
                fn = mig.get("filename", "002_tables.sql")
                all_files.append({"path": f"supabase/migrations/{fn}", "content": mig["content"]})

        # Add Copywriter messages files (FR + EN)
        messages_fr = input_data.get("messages_fr", {})
        messages_en = input_data.get("messages_en", {})
        if messages_fr:
            all_files.append({"path": "messages/fr.json", "content": json.dumps(messages_fr, ensure_ascii=False, indent=2)})
            all_files.append({"path": "src/messages/fr.json", "content": json.dumps(messages_fr, ensure_ascii=False, indent=2)})
        if messages_en:
            all_files.append({"path": "messages/en.json", "content": json.dumps(messages_en, ensure_ascii=False, indent=2)})
            all_files.append({"path": "src/messages/en.json", "content": json.dumps(messages_en, ensure_ascii=False, indent=2)})

        if not all_files:
            logger.warning("no_files_to_push")
            return {"pushed_files": [], "repo": github_repo}

        result = await self._batch_commit(
            github_repo, all_files,
            f"feat: add generated business code ({len(all_files)} files)"
        )

        await self.log_execution(
            action="push_to_github",
            result={"files_pushed": result.get("files", 0), "repo": github_repo},
            business_id=business_id,
        )

        return {"pushed_files": [{"path": f["path"]} for f in all_files], "repo": github_repo}

    async def deploy_vercel(self, context) -> dict:
        """Step 6: Create Vercel project linked to GitHub repo and trigger deploy."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        repo_info = context.step_output("create_github_repo")
        github_repo = repo_info.get("repo", "")

        token = settings.get("VERCEL_TOKEN")
        if not token:
            logger.warning("vercel_token_missing")
            await self.log_execution(
                action="deploy_vercel", result={"skipped": True, "reason": "VERCEL_TOKEN not configured"},
                business_id=business_id,
            )
            return {"deployment_url": None, "success": False, "error": "VERCEL_TOKEN not configured"}

        if not github_repo:
            return {"deployment_url": None, "success": False, "error": "No GitHub repo"}

        repo_parts = github_repo.split("/")
        repo_name = repo_parts[-1] if repo_parts else github_repo

        async with httpx.AsyncClient(timeout=60) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            try:
                # Create Vercel project linked to GitHub
                create_resp = await client.post(
                    "https://api.vercel.com/v10/projects",
                    headers=headers,
                    json={
                        "name": repo_name,
                        "framework": "nextjs",
                        "gitRepository": {
                            "type": "github",
                            "repo": github_repo,
                        },
                    },
                )
                if create_resp.status_code in (200, 201):
                    project = create_resp.json()
                    project_id = project.get("id", "")
                    logger.info("vercel_project_created", project_id=project_id, name=repo_name)

                    if business_id:
                        async with SessionLocal() as db:
                            await db.execute(text(
                                "UPDATE businesses SET vercel_project_id = :pid, updated_at = NOW() WHERE id = :id"
                            ), {"pid": project_id, "id": business_id})
                            await db.commit()
                elif create_resp.status_code == 409:
                    logger.info("vercel_project_exists", name=repo_name)
                    project_id = repo_name
                else:
                    logger.error("vercel_project_create_failed", status=create_resp.status_code, body=create_resp.text[:300])
                    return {"deployment_url": None, "success": False, "error": f"Vercel project create: {create_resp.status_code}"}

                # Get repo ID from GitHub for Vercel
                gh_token = settings.get("GITHUB_TOKEN")
                gh_resp = await client.get(
                    f"https://api.github.com/repos/{github_repo}",
                    headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                )
                repo_id = str(gh_resp.json().get("id", "")) if gh_resp.status_code == 200 else ""

                # Trigger deployment
                deploy_resp = await client.post(
                    "https://api.vercel.com/v13/deployments",
                    headers=headers,
                    json={
                        "name": repo_name,
                        "gitSource": {"type": "github", "repoId": repo_id, "ref": "main"},
                    },
                )
                if deploy_resp.status_code in (200, 201):
                    deployment = deploy_resp.json()
                    deploy_url = deployment.get("url", "")
                    deploy_id = deployment.get("id", "")
                    logger.info("vercel_deployed", url=deploy_url, id=deploy_id)

                    if business_id and deploy_url:
                        async with SessionLocal() as db:
                            await db.execute(text(
                                "UPDATE businesses SET domain = :domain, updated_at = NOW() WHERE id = :id"
                            ), {"domain": deploy_url, "id": business_id})
                            await db.commit()

                    # Track Vercel usage/cost
                    vercel_cost = 0.0
                    try:
                        usage_resp = await client.get(
                            "https://api.vercel.com/v2/usage",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if usage_resp.status_code == 200:
                            usage = usage_resp.json()
                            # Vercel Pro = $20/mo base. Per-project cost estimate.
                            project_count = max(usage.get("projectCount", 1), 1)
                            vercel_cost = round(20.0 / project_count / 30, 4)  # daily amortized per project
                    except Exception:
                        pass

                    await self.log_execution(
                        action="deploy_vercel",
                        result={"url": deploy_url, "id": deploy_id},
                        cost_usd=vercel_cost,
                        business_id=business_id,
                    )
                    return {"deployment_url": deploy_url, "deployment_id": deploy_id, "success": True, "cost_usd": vercel_cost}
                else:
                    logger.error("vercel_deploy_failed", status=deploy_resp.status_code, body=deploy_resp.text[:300])
                    return {"deployment_url": None, "success": False, "error": f"Vercel deploy: {deploy_resp.status_code}"}

            except Exception as exc:
                logger.error("vercel_deploy_error", error=str(exc))
                return {"deployment_url": None, "success": False, "error": str(exc)}

    async def run_lighthouse(self, context) -> dict:
        """Step 7: Run Lighthouse audit on the deployed site via PageSpeed Insights API."""
        deploy = context.step_output("deploy_vercel")
        url = deploy.get("deployment_url")

        if not url:
            return {"lighthouse_scores": None, "reason": "no deployment URL"}

        # Wait a bit for deployment to be ready
        import asyncio
        await asyncio.sleep(30)

        async with httpx.AsyncClient(timeout=90) as client:
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
                    await self.log_execution(
                        action="run_lighthouse",
                        result={"scores": scores, "url": url},
                    )
                    return {"lighthouse_scores": scores, "url": url}
                logger.warning("lighthouse_failed", status=resp.status_code)
                return {"lighthouse_scores": None, "status": resp.status_code}
            except Exception as exc:
                logger.warning("lighthouse_error", error=str(exc))
                return {"lighthouse_scores": None, "error": str(exc)}

    async def finalize(self, context) -> dict:
        """Step 8: Update business status and log completion."""
        input_data = context.workflow_input()
        business_id = input_data.get("business_id")
        repo_info = context.step_output("create_github_repo")
        push_info = context.step_output("push_to_github")
        deploy_info = context.step_output("deploy_vercel")
        lighthouse_info = context.step_output("run_lighthouse")

        github_repo = repo_info.get("repo", "")
        files_pushed = len(push_info.get("pushed_files", []))
        deploy_url = deploy_info.get("deployment_url")
        lighthouse = lighthouse_info.get("lighthouse_scores")

        final_status = "pre_launch" if deploy_url else "building"

        async with SessionLocal() as db:
            if business_id:
                await db.execute(
                    text(
                        "UPDATE businesses SET status = :status, github_repo = :repo, "
                        "updated_at = NOW() WHERE id = :id"
                    ),
                    {"status": final_status, "repo": github_repo, "id": business_id},
                )
                await db.commit()

        await self.log_execution(
            action="build_complete",
            result={
                "business_id": business_id,
                "github_repo": github_repo,
                "files_pushed": files_pushed,
                "deployment_url": deploy_url,
                "lighthouse_scores": lighthouse,
                "status": final_status,
            },
            business_id=business_id,
        )

        return {
            "business_id": business_id,
            "github_repo": github_repo,
            "files_pushed": files_pushed,
            "deployment_url": deploy_url,
            "lighthouse_scores": lighthouse,
            "status": final_status,
        }


def register(hatchet_instance):
    """Register Builder as a Hatchet workflow."""
    agent = Builder()
    wf = hatchet_instance.workflow(name="builder")

    @wf.task(execution_timeout="10m", retries=2)
    async def generate_architecture(input, ctx):
        return await agent.generate_architecture(ctx)

    @wf.task(execution_timeout="10m", retries=2)
    async def generate_code(input, ctx):
        return await agent.generate_code(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def verify_rls(input, ctx):
        return await agent.verify_rls(ctx)

    @wf.task(execution_timeout="5m", retries=2)
    async def create_github_repo(input, ctx):
        return await agent.create_github_repo(ctx)

    @wf.task(execution_timeout="10m", retries=1)
    async def push_template(input, ctx):
        return await agent.push_template(ctx)

    @wf.task(execution_timeout="5m", retries=2)
    async def push_to_github(input, ctx):
        return await agent.push_to_github(ctx)

    @wf.task(execution_timeout="5m", retries=2)
    async def deploy_vercel(input, ctx):
        return await agent.deploy_vercel(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def run_lighthouse(input, ctx):
        return await agent.run_lighthouse(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def finalize(input, ctx):
        return await agent.finalize(ctx)

    return wf

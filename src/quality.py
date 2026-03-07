"""Quality gates — pre-send email review + pre-deploy security scan.

Called by Outreach Agent and Builder Agent before executing actions.
"""

from __future__ import annotations

import json
import re

import structlog

from src.llm import call_claude

logger = structlog.get_logger()

QUALITY_REVIEW_PROMPT = """\
You are a quality reviewer for cold B2B emails targeting Canadian businesses.

Rate this cold email 1-10 on each criterion:
1. Natural tone (doesn't sound AI-generated)
2. No AI-sounding phrases ("leverage", "streamline", "I hope this finds you well")
3. Correct québécois French (tutoiement, natural expressions) — or correct English if EN
4. CASL compliance (implied consent for B2B, relevant to recipient's role)
5. Relevance to ICP (addresses a real pain point, not generic)

Respond in JSON:
{"scores": {"natural_tone": 8, "no_ai_phrases": 7, "language_quality": 9, "casl": 10, "relevance": 8}, "overall": 8.4, "issues": ["list of specific issues"], "pass": true}

Set "pass" to false if ANY individual score is below 6.
"""

SECURITY_PATTERNS = [
    (r'sk[-_](?:live|test)[-_][a-zA-Z0-9]{20,}', "Stripe secret key exposed"),
    (r'sk-ant-api[a-zA-Z0-9\-_]{20,}', "Anthropic API key exposed"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub token exposed"),
    (r'SUPABASE_SERVICE_ROLE_KEY\s*=\s*["\'][^"\']+', "Supabase service role key exposed"),
    (r'password\s*=\s*["\'][^"\']{8,}', "Hardcoded password"),
]


async def quality_check_emails(emails: list[dict], *, sample_size: int = 3) -> dict:
    """Sample random emails and run quality review via Claude.

    Returns {"passed": bool, "results": [...], "blocked_count": int}.
    """
    import random
    sample = random.sample(emails, min(sample_size, len(emails)))

    results = []
    blocked = 0

    for email in sample:
        subject = email.get("subject", "")
        body = email.get("body", "")

        response, cost = await call_claude(
            model_tier="haiku",
            system=QUALITY_REVIEW_PROMPT,
            user=f"Subject: {subject}\n\nBody:\n{body}",
            max_tokens=256,
            temperature=0.1,
        )

        try:
            review = json.loads(response)
        except json.JSONDecodeError:
            review = {"pass": False, "issues": ["Failed to parse quality review"]}

        passed = review.get("pass", True)
        if not passed:
            blocked += 1

        results.append({
            "subject": subject[:50],
            "overall": review.get("overall"),
            "passed": passed,
            "issues": review.get("issues", []),
        })

    all_passed = blocked == 0
    if not all_passed:
        logger.warning("quality_gate_blocked", blocked=blocked, sample_size=len(sample))

    return {"passed": all_passed, "results": results, "blocked_count": blocked}


def security_scan_code(files: list[dict]) -> dict:
    """Scan generated code for exposed secrets, hardcoded passwords.

    Returns {"passed": bool, "issues": [{"file": str, "issue": str, "severity": "critical"|"warning"}]}.
    """
    issues = []

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")

        # Skip non-frontend files
        if not content:
            continue

        for pattern, description in SECURITY_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append({
                    "file": path,
                    "issue": description,
                    "severity": "critical",
                })

        # Check for env vars in frontend code
        if "NEXT_PUBLIC_" not in path and ("process.env." in content or "import.meta.env" in content):
            if any(secret in content for secret in ["SECRET", "PASSWORD", "PRIVATE", "SERVICE_ROLE"]):
                issues.append({
                    "file": path,
                    "issue": "Server-side secret accessed in potentially client-side code",
                    "severity": "warning",
                })

    critical = [i for i in issues if i["severity"] == "critical"]
    return {
        "passed": len(critical) == 0,
        "issues": issues,
        "critical_count": len(critical),
    }

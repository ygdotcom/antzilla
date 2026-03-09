# Antzilla

**An autonomous business engine.** Discovers SaaS ideas that work in the US but don't exist in Canada, builds fully functional apps, markets them via cold email + AI voice calls, and operates them — all from a single dashboard.

32 autonomous agents. One "Approve" click builds a complete SaaS in ~8 minutes for ~$0.60.

```
391 tests | 17,000+ lines of Python | 80+ source files
Supabase Auth | HTTPS | hub.antzilla.ca
```

---

## What It Actually Does

```
Approve an idea
    ↓
Brand Designer generates colors, fonts, name           (~$0.06, 12s)
    ↓
Architect designs pages, DB tables, API routes          (~$0.15, 25s)
    ↓
Copywriter writes all text in French + English          (~$0.06, 15s)
    ↓
Builder generates Next.js code with real Supabase CRUD  (~$0.25, 2min)
    ↓
Pushes to GitHub (template + generated code, 2 commits)
    ↓
Deploys to Vercel (auto-build from Git)
    ↓
Infra Setup: Supabase tables + Stripe products + env vars
    ↓
Design QA: generates SVG logo + reviews design
    ↓
Live app with auth, billing, dashboard, CRUD             Total: ~$0.60
```

Each generated app includes:
- Supabase Auth (signup/login with password)
- Stripe billing (Free $0 / Pro $49 / Business $99 CAD)
- Real CRUD dashboard with Server Actions
- Bilingual FR/EN (auto-detects browser language)
- RLS on every table
- Google Analytics
- Brand colors + custom logo

---

## Architecture

```
CEO Dashboard (hub.antzilla.ca)
  FastAPI + HTMX + Tailwind
  Notifications · Console · Rebuild · Approve/Kill
        │
        ▼
  Postgres + pgvector
  25 tables · encrypted secrets · knowledge base
        │
  ┌─────┼─────────────────────────────┐
  │     │                             │
  ▼     ▼                             ▼
Hatchet Engine         Factory Worker (32 agents)
  Cron scheduling       Brand · Copy · Build · Deploy
  DAG workflows         Leads · Enrich · Outreach · Voice
  Retries               Analytics · Self-Reflection
```

---

## Pipeline: Idea → Live Business

```
 DISCOVER              BUILD                 SELL                 OPERATE
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│Idea Factory│──▶│Brand Designer│──▶│Lead Pipeline │──▶│Billing Agent │
│Deep Scout │    │Copywriter    │    │Enrichment    │    │Support Agent │
│  (auto)   │    │Builder       │    │Outreach      │    │Analytics     │
│           │    │Infra Setup   │    │Reply Handler │    │Self-Reflect  │
│           │    │Design QA     │    │Voice Agent   │    │Knowledge     │
└──────────┘    └──────────────┘    └──────────────┘    └──────────────┘
   Claude           Claude              Apollo             Stripe
   Serper           Vercel              Instantly           Resend
                    GitHub              Retell AI           Twilio
                    Supabase            ZeroBounce
                    Stripe
```

---

## All 32 Agents

| # | Agent | Trigger | What It Does |
|---|-------|---------|-------------|
| 1 | Meta Orchestrator | Daily 6AM | Coordinates all agents, Slack digest |
| 2 | Idea Factory | Weekly Mon 5AM | Finds small SaaS gaps (all of Canada, deduplication) |
| 3 | Deep Scout | Auto (score ≥ 7) | Market research + GTM Playbook |
| 4 | Validator | On-demand | $150 ad test, GO/KILL |
| 5 | Brand Designer | Auto (on approve) | Colors, fonts, name, domain check |
| 6 | Domain Provisioner | On-demand | Full infra: domains, DNS, services |
| 7 | Builder | Auto (on approve) | 3-call code gen, GitHub push, Vercel deploy |
| 8 | i18n | Weekly Sun | FR/EN key validation |
| 9 | Content Engine | Mon+Thu | Editorial + programmatic SEO |
| 10 | Social Agent | 3x/day | Community monitoring, LinkedIn posts |
| 11 | Referral | Weekly | NPS-triggered double-sided referrals |
| 12a | Lead Pipeline | Daily | Google Maps leads via Serper |
| 12b | Enrichment | Daily (after leads) | Apollo → Hunter → ZeroBounce |
| 12c | Signal Monitor | Every 4h | Buying signals, permit data |
| 12d | Outreach | Daily | Cold email via Instantly (tiered autonomy) |
| 12e | Reply Handler | Every 30min | Classify + route (positive → Voice Agent) |
| 13 | Email Nurture | Mon+Thu | 4 sequences, 3/week cap |
| 14 | Social Proof | Monthly | Testimonial requests, review invites |
| 15 | Competitor Watch | Weekly Wed | Scrape competitors, Product Hunt |
| 16 | Fulfillment | On-demand | Claude-based generic handler |
| 17 | Billing Agent | Daily + webhook | Stripe dunning, pre-expiry alerts |
| 18 | Support Agent | Daily | Claude RAG responses, feature extraction |
| 19 | Upsell | Weekly Mon | Usage-based offers, 1/month cap |
| 20 | Onboarding | Daily | Stall nudges at 24h/72h |
| 21 | Analytics | Nightly | Kill score 0-100, teardown workflow |
| 22 | Self-Reflection | Weekly | Opus analysis of all agents |
| 23 | Legal Guardrail | Weekly + events | CASL, DNCL, PIPEDA compliance |
| 24 | DevOps | Every 15min + daily | Health checks (state-change alerts only), backups |
| 25 | Budget Guardian | Hourly | Throttle at 90%, pause at 95% |
| 26 | Voice Agent | Auto (from replies) | Retell AI warm calls, DNCL checked |
| 27 | Growth Hacker | Weekly Tue | Tactic scoring + execution |
| 28 | Knowledge | Weekly Sun | Cross-business pattern extraction |
| 29 | Design QA | Auto (after build) | Logo generation + design review |
| 30 | Copywriter | Auto (in pipeline) | FR+EN copy, conversion-optimized |
| 31 | Infra Setup | Auto (in pipeline) | Supabase + Stripe + Vercel env vars |

---

## Safety Systems

| System | How It Works |
|--------|-------------|
| Budget Circuit Breaker | Every Claude call checks spend. 80% → Haiku. 90% → write MODEL_OVERRIDE. 95% → pause agents. |
| Quality Gate | Outreach samples 3 emails via Claude before sending. Builder security-scans code. |
| Human Touchpoint | Hot leads (score ≥ 80) → Slack with approve link. First 5 customers → always human. |
| Warm Calls Only | Voice Agent blocks cold leads. DNCL checked via CRTC API. |
| RLS Verification | Every generated migration checked for ENABLE ROW LEVEL SECURITY. Auto-fixes. |
| Code Sanitizer | Fixes common Claude mistakes (missing newlines, missing await) before push. |
| Graceful Infra | Missing API keys skip that step, don't crash the pipeline. |

---

## Dashboard

Live at **https://hub.antzilla.ca** (Supabase Auth login).

Pages: Overview, Businesses (with rebuild), Ideas (multi-filter), Agents, Budget, Decisions, Console (real-time), Knowledge, Settings (API keys + team).

Notification bell polls every 10s. Validated ideas show as pending approvals. Slack notifications include clickable dashboard links.

---

## API Keys

Configure in Settings. Only 3 are required to build apps:

| Key | Required For | Status |
|-----|-------------|--------|
| `ANTHROPIC_API_KEY` | All Claude reasoning | Required |
| `GITHUB_TOKEN` | Push code to repos | Required |
| `VERCEL_TOKEN` | Deploy apps | Required |
| `STRIPE_SECRET_KEY` | Billing setup | For payments |
| `APOLLO_API_KEY` | Lead enrichment | For distribution |
| `INSTANTLY_API_KEY` | Cold email | For outreach |
| `RESEND_API_KEY` | Transactional email | For nurture |
| `RETELL_API_KEY` | AI voice calls | For warm calls |
| `TWILIO_*` | Phone infrastructure | For voice |
| `SLACK_WEBHOOK_URL` | Notifications | Recommended |

---

## Quick Start

```bash
# Local
cp .env.example .env
docker compose up -d
# Dashboard: https://localhost

# Tests
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/     # 391 tests, ~3 seconds

# Deploy to GCP (Montreal)
bash scripts/deploy-gcp.sh

# Update
bash scripts/update.sh
```

---

## Project Structure

```
antzilla/
├── docker-compose.yml                # 8 services
├── Caddyfile                         # HTTPS + hub.antzilla.ca
├── Dockerfile + Dockerfile.dashboard
├── .env.example                      # Boot variables only
├── SPEC.md                           # Full specification
│
├── src/
│   ├── main.py                       # Registers all 32 workflows
│   ├── config.py                     # DB-first secrets
│   ├── crypto.py                     # AES-256-GCM
│   ├── db.py                         # SQLAlchemy async
│   ├── llm.py                        # call_claude() with streaming + cost
│   ├── slack.py                      # Rich notifications with links
│   ├── quality.py                    # Email quality + security scan
│   ├── knowledge.py                  # Cross-business learning
│   │
│   ├── agents/                       # 32 agent files
│   │   ├── base_agent.py
│   │   ├── builder.py                # 3-call code gen + sanitizer
│   │   ├── infra_setup.py            # Supabase + Stripe + Vercel env
│   │   ├── design_qa.py              # Logo + visual review
│   │   ├── copywriter.py             # FR+EN conversion copy
│   │   └── distribution/             # 5 sub-agents
│   │
│   ├── integrations/                 # 11 API clients
│   │
│   └── dashboard/
│       ├── app.py                    # Build pipeline + notifications
│       ├── deps.py                   # Supabase Auth + sessions
│       ├── routes/                   # 10 route modules
│       └── templates/                # 12 Jinja2 templates
│
├── template-repo/                    # Next.js 15 template
│   ├── src/components/ui/            # Card, Button, Badge, Input
│   ├── src/lib/supabase/             # Pre-configured client
│   ├── supabase/migrations/          # RLS-enforced schema
│   └── src/app/[locale]/             # i18n routing
│
├── prompts/                          # System prompts
├── migrations/                       # Antzilla DB schema
├── scripts/                          # Deploy, setup, seed
└── tests/                            # 391 tests
```

---

## License

Private.

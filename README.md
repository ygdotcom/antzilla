# Factory

**An autonomous business factory.** Discovers SaaS ideas that work in the US but don't exist in Canada, validates them with real ads, builds MVPs, markets them for $0, sells via cold email + AI voice calls, and operates them — all with ~2-3 hours/week of human oversight.

32 autonomous agents orchestrated by [Hatchet](https://hatchet.run), running on a single GCP VM with Docker.

```
381 tests | 13,500 lines of Python | 69 source files | Supabase Auth | HTTPS
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           CEO DASHBOARD (:9000)                              │
│                  FastAPI + HTMX + Tailwind (dark theme)                      │
│   Setup Wizard · Settings · Budget sliders · Kill/GO buttons · Knowledge     │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ reads/writes
┌──────────────────────────────▼───────────────────────────────────────────────┐
│                        POSTGRES + pgvector (:5432)                            │
│    25 tables · shared state · vector embeddings · encrypted secrets store     │
└──────┬───────────┬───────────┬───────────┬───────────┬───────────┬───────────┘
       │           │           │           │           │           │
┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐
│ HATCHET │ │PLAUSIBLE│ │ UPTIME  │ │CLICKHSE │ │ FACTORY │ │  DASH   │
│ ENGINE  │ │Analytics│ │  KUMA   │ │(Plausbl)│ │ WORKER  │ │  BOARD  │
│  :8080  │ │  :8000  │ │  :3001  │ │         │ │(agents) │ │  :9000  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

---

## How It Works

```
  DISCOVER          VALIDATE          BUILD            SELL              OPERATE
 ┌────────┐       ┌─────────┐      ┌────────┐      ┌─────────┐       ┌─────────┐
 │ Idea   │──▶──│ Validator│──▶──│Builder │──▶──│Distribtn│──▶──│Billing  │
 │Factory │  │   │  $150   │  │   │ Next.js│  │   │ Engine  │  │   │Support  │
 │  +     │  │   │  ads    │  │   │ + RLS  │  │   │ 5 sub-  │  │   │Referral │
 │ Deep   │  │   │ GO/KILL │  │   │ + i18n │  │   │ agents  │  │   │Upsell   │
 │ Scout  │  │   └─────────┘  │   └────────┘  │   └─────────┘  │   └─────────┘
 └────────┘  │                │               │                │
             │   ┌─────────┐  │  ┌─────────┐  │  ┌──────────┐  │  ┌──────────┐
             └──│  Brand  │  └─│ Domain  │  └─│  Content │  └─│ Analytics│
                │ Designer│    │Provisnr │    │  Engine  │    │ Kill Score│
                └─────────┘    └─────────┘    │  Social  │    │Knowledge │
                                              │  Growth  │    │Self-Refl │
                                              └──────────┘    └──────────┘
```

---

## Agent System — 32 Workflows

All agents inherit from `BaseAgent`: budget circuit breaker (auto-downgrades model tier), execution logging, Slack alerting.

### Wave 1 — Ship and Sell (Days 1-10)

| # | Agent | Trigger | Model | Key feature |
|---|-------|---------|-------|-------------|
| 1 | Meta Orchestrator | Cron 6AM daily | Opus | CEO coordinator, triggers all others |
| 2 | Idea Factory | Cron Monday 5AM | Sonnet | 12-criteria scoring, Canadian gap filter |
| 3 | Deep Scout | On-demand | Opus | Scout Report + GTM Playbook (knowledge-informed) |
| 4 | Validator | On-demand | Sonnet | $150 ads test, hardcoded GO/KILL rules |
| 5 | Brand Designer | On-demand | Opus | Light + full mode, domain availability |
| 6 | Domain Provisioner | On-demand | Sonnet | 12-step infra: .ca + .io/.co cold domains |
| 7 | Builder | On-demand | Opus+Sonnet | RLS verification + security scan gates |
| 21 | Analytics & Kill | Cron 11PM | Sonnet | Kill score 0-100, teardown workflow |

### Distribution Engine — 5 Sub-agents

The revenue engine. Reads from `gtm_playbooks` — change verticals via config, not code.

| # | Agent | Key feature |
|---|-------|-------------|
| 12a | Lead Pipeline | Google Maps, RBQ, REQ, Federal Corp, associations |
| 12b | Enrichment | Waterfall: Apollo → Hunter → scrape. Lead scoring 0-100 |
| 12c | Signal Monitor | REQ registrations, building permits, competitor complaints |
| 12d | Outreach | Tiered autonomy + quality gate (samples 3 emails via Claude) |
| 12e | Reply Handler | 8 categories, human touchpoint for hot leads + first 5 customers |

### Wave 2 — Grow (Week 3-4)

| # | Agent | Key feature |
|---|-------|-------------|
| 9 | Content Engine | Editorial + programmatic SEO (6 templates × verticals × provinces) |
| 10 | Social Agent | Syften monitoring, 90/10 anti-ban, brand reputation monitor |
| 11 | Referral | NPS ≥ 9 instant invite, SMS priority, double-sided, ambassadors |
| 26 | Voice Agent | **Warm calls only**, DNCL checked, 9AM-9:30PM calling hours |
| 17 | Billing | Reverse trial, 4-email dunning, pre-expiry SMS, CA taxes |
| 18 | Support | RAG via pgvector, bilingual, feature request accumulation |
| 8 | i18n | FR/EN key validation, québécois quality check |
| 13 | Email Nurture | 4 sequences, max 3/week/user frequency cap |

### Wave 3 — Optimize (Month 2+)

| # | Agent | Key feature |
|---|-------|-------------|
| 20 | Onboarding | Nudge at 24h/72h, aha moment detection, trigger referral |
| 19 | Upsell | Usage-based, max 1 offer/month/customer |
| 14 | Social Proof | NPS ≥ 8 testimonial requests, Google/Capterra reviews |
| 15 | Competitor Watch | Weekly scrape, pricing changes, Product Hunt launches |
| 16 | Fulfillment | Registry pattern, per-business handlers |
| 22 | Self-Reflection | Opus: synthesizes ALL agents + ALL businesses weekly |
| 23 | Legal Guardrail | CASL, CRTC, PIPEDA, Loi 101, billing dark patterns |
| 24 | DevOps | 5-min health checks, daily backups, monthly restore test |
| 25 | Budget Guardian | $50/day hard cap, cash flow per business, runway calc |
| 27 | Growth Hacker | 12 tactic types, marketplace listing, template bait |
| 28 | Knowledge | Cross-business learning, scoring calibration, meta-synthesis |

---

## Safety Systems

| System | What it does |
|--------|-------------|
| **Budget Circuit Breaker** | Every Claude call checks daily spend. 80% → downgrade model. 100% → hard stop. |
| **Quality Gate** | Outreach samples 3 emails via Claude before batch send. Builder security-scans code for exposed keys. |
| **Human Touchpoint** | Hot leads (score ≥ 80) → Slack. First 5 customers → always human. |
| **Warm Calls Only** | Voice Agent blocks `new`, `contacted`, `enriched` leads. DNCL checked. $15K/call fine prevention. |
| **RLS Verification** | Builder regex-checks every `CREATE TABLE` for matching `ENABLE ROW LEVEL SECURITY`. Auto-fixes violations. |
| **Brand Monitor** | Negative sentiment < 0.3 → pause all social activity + Slack alert. |
| **Teardown** | Kill button → cancel Instantly, Vercel, Stripe, Twilio, archive GitHub, mark leads. |
| **Backup Restore** | Monthly: dump → restore to temp DB → verify → drop. Alerts if fails. |
| **Legal Guardrail** | CASL unsub processing, CRTC calling hours, Loi 101 FR content, PIPEDA data handling. |

---

## Knowledge Accumulation

The factory gets smarter with each business. Agent 28 (Knowledge Agent) extracts cross-business patterns weekly:

| Category | Example |
|----------|---------|
| `email_template_winner` | "Timeline hooks beat pain hooks 2.3x for trades" |
| `channel_effectiveness` | "Facebook Groups has 3x lower CAC than cold email in QC" |
| `idea_scoring_calibration` | "Ideas scoring 8+ on defensibility underperform — lower weight" |
| `objection_response` | "Pricing objections convert 40% when responding with ROI calc" |
| `churn_reason` | "Trades customers churn after avg 12 days inactivity" |

Insights flow into: Deep Scout (GTM Playbooks), Outreach (email templates), Idea Factory (scoring weights), Reply Handler (objection responses).

---

## Auth and Secrets

**Dashboard login** is via [Supabase Auth](https://supabase.com/auth) (email/password). First user gets admin role. Invite team members from Settings with roles (admin/operator/viewer). Session stored in HMAC-signed cookie.

**API keys** are stored **AES-256-GCM encrypted** in the `secrets` table. The `.env` only has boot variables (Postgres password, encryption key, Supabase URL). First boot → Setup Wizard at `/setup` with 5 steps and test buttons per key.

**HTTPS** via Caddy reverse proxy with auto-TLS. HTTP redirects to HTTPS.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Orchestration | Hatchet (DAG workflows, cron, retries, dashboard) |
| Auth | Supabase Auth (email/password, team invites, roles) |
| LLM | Claude Opus/Sonnet/Haiku (auto-downgrading at budget limits) |
| Database | Postgres + pgvector (CRM + RAG + secrets + knowledge) |
| Reverse proxy | Caddy (automatic HTTPS, HTTP→HTTPS redirect) |
| DNS | Cloudflare |
| Domains | Namecheap (.ca + secondary cold email domains) |
| Hosting | Vercel (per-business Next.js apps) |
| Payments | Stripe (CAD, reverse trial, Stripe Tax) |
| Cold email | Instantly.ai (secondary domains only, 4-6 week warmup) |
| Voice | Retell AI + Twilio ($0.07/min, warm calls only) |
| Analytics | Plausible (self-hosted, no cookie consent) |
| Monitoring | Uptime Kuma (self-hosted health checks) |

---

## Quick Start

```bash
# Local development
cp .env.example .env    # Add Supabase keys + generate ENCRYPTION_KEY
docker compose up -d
# Dashboard: https://localhost  (login with Supabase user)

# Run tests
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v    # 381 tests, ~1 second

# Deploy to GCP (Montreal, e2-standard-4, 200GB SSD)
bash scripts/deploy-gcp.sh

# Update deployed instance
bash scripts/update.sh
```

---

## Project Structure

```
factory/
├── docker-compose.yml              # 8 services
├── Dockerfile                       # Factory worker
├── Dockerfile.dashboard             # CEO Dashboard
├── .env.example                     # 6 boot variables only
├── SPEC.md                          # Complete specification
│
├── src/
│   ├── main.py                      # Registers all 32+ workflows
│   ├── config.py                    # DB-first secrets with get()
│   ├── crypto.py                    # AES-256-GCM encrypt/decrypt
│   ├── db.py                        # SQLAlchemy async engine
│   ├── llm.py                       # call_claude() with cost tracking
│   ├── quality.py                   # Email quality gate + security scan
│   ├── knowledge.py                 # Cross-business knowledge queries
│   │
│   ├── agents/                      # 32 agent files
│   │   ├── base_agent.py            # Budget circuit breaker
│   │   ├── meta_orchestrator.py     # through growth_hacker.py
│   │   ├── knowledge_agent.py       # Agent 28: long-term memory
│   │   └── distribution/            # 5 sub-agents
│   │
│   ├── integrations/                # 11 API clients
│   │
│   └── dashboard/                   # CEO Dashboard
│       ├── app.py + deps.py
│       ├── routes/                  # 9 route modules
│       └── templates/               # 10 Jinja2 templates
│
├── template-repo/                   # Next.js 15 template for businesses
├── migrations/001_init.sql          # 25 tables + indexes
├── prompts/                         # 4 system prompts
├── scripts/                         # deploy, setup, seed, update
└── tests/                           # 378 tests across 15 files
```

---

## License

Private.

# Factory

**An autonomous business factory.** Discovers SaaS ideas that work in the US but don't exist in Canada, validates them with real ads, builds MVPs, markets them for $0, sells via cold email + AI voice calls, and operates them — all with ~2-3 hours/week of human oversight.

31 autonomous agents orchestrated by [Hatchet](https://hatchet.run), running on a single VPS with Docker.

```
314 tests | 16,630 lines of Python | 77 source files | 0 external SaaS for CRM
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           CEO DASHBOARD (:9000)                              │
│                  FastAPI + HTMX + Tailwind (dark theme)                      │
│         Budget sliders · Kill/GO buttons · Outreach approval queue           │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ reads/writes
┌──────────────────────────────▼───────────────────────────────────────────────┐
│                        POSTGRES + pgvector (:5432)                            │
│  22 tables · shared state · vector embeddings for RAG · the CRM IS Postgres  │
└──────┬───────────┬───────────┬───────────┬───────────┬───────────┬───────────┘
       │           │           │           │           │           │
┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐ ┌──────▼──┐
│ HATCHET │ │PLAUSIBLE│ │ UPTIME  │ │CLICKHSE │ │ FACTORY │ │  DASH   │
│ ENGINE  │ │Analytics│ │  KUMA   │ │(Plausbl)│ │ WORKER  │ │  BOARD  │
│  :8080  │ │  :8000  │ │  :3001  │ │         │ │(agents) │ │  :9000  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

---

## Agent System — 31 Workflows Across 3 Waves

All agents inherit from `BaseAgent` which provides: budget circuit breaker (auto-downgrades Claude model tier at 80%, hard stop at 100%), execution logging to `agent_logs`, Slack alerting, and error tracking.

### Wave 1 — Ship and Sell (Days 1-10)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     META ORCHESTRATOR (Agent 1)                         │
│              Cron 6AM ET · Claude Opus · CEO of the factory             │
│     Reads all metrics → decides priorities → triggers other agents      │
└────────┬──────────┬──────────┬──────────┬──────────┬────────────────────┘
         │          │          │          │          │
    ┌────▼───┐ ┌────▼───┐ ┌────▼────┐ ┌──▼───┐ ┌───▼────┐
    │ IDEA   │ │ DEEP   │ │VALIDATR │ │BRAND │ │DOMAIN  │
    │FACTORY │ │ SCOUT  │ │  (4)    │ │DESIGN│ │PROVISNR│
    │  (2)   │ │  (3)   │ │         │ │ (5)  │ │  (6)   │
    │Weekly  │ │On-demnd│ │$150 ads │ │Light │ │.ca+.io │
    │Sonnet  │ │ Opus   │ │ GO/KILL │ │+Full │ │+.co DNS│
    └───┬────┘ └───┬────┘ └────┬────┘ └──┬───┘ └───┬────┘
        │          │           │         │         │
        │   Score  │  Scout    │ Signup  │ Brand   │ Infra
        │   ≥ 7.0  │  Report   │ rate    │ kit     │ ready
        │          │  + GTM    │ > 5%    │ JSONB   │
        │          │  Playbook │ = GO    │         │
        │          │           │         │         │
    ┌───▼──────────▼───────────▼─────────▼─────────▼────┐
    │              BUILDER (Agent 7)                      │
    │  Claude Opus → architecture                        │
    │  Claude Sonnet → code generation                   │
    │  RLS verification gate (§12 — NON-NEGOTIABLE)      │
    │  Push to GitHub → Deploy to Vercel → Lighthouse    │
    └───────────────────────┬────────────────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │  ANALYTICS & KILL   │
                 │     (Agent 21)      │
                 │  Kill score 0-100   │
                 │  <30 after 8w = KILL│
                 └─────────────────────┘
```

### Distribution Engine (Agent 12 — 5 Sub-agents)

**The revenue engine.** Reads everything from `gtm_playbooks` config — changing verticals means changing the playbook JSON, not the code.

```
                    ┌─────────────────────┐
                    │    GTM PLAYBOOK     │
                    │  (gtm_playbooks DB) │
                    │  ICP · Channels ·   │
                    │  Lead sources ·     │
                    │  Signals · Messaging│
                    └──────────┬──────────┘
                               │ configures all ↓
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────▼─────┐         ┌─────▼────┐          ┌────▼─────┐
    │  LEAD    │         │ SIGNAL   │          │ OUTREACH │
    │ PIPELINE │         │ MONITOR  │          │  AGENT   │
    │  (12a)   │         │  (12c)   │          │  (12d)   │
    │ Google   │         │ REQ new  │          │ Claude   │
    │ Maps,RBQ │         │ biz regs │          │ Haiku    │
    │ REQ,Fed  │         │ Permits  │          │ <80 words│
    │ Assoc.   │         │ Reviews  │          │ TIERED   │
    └────┬─────┘         │ Indeed   │          │ AUTONOMY │
         │               │ Plausble │          │          │
    ┌────▼─────┐         └─────┬────┘          │ Wk 1-2: │
    │ENRICHMNT │               │bumps          │  Slack   │
    │  (12b)   │               │score          │  review  │
    │ Apollo → │               │               │ Wk 3-4: │
    │ Hunter → │               │               │  Auto    │
    │ Scrape   │               │               │  <70     │
    │ZeroBonce │               │               │ Mo 2+:  │
    │ Score    │               │               │  Full    │
    │ 0-100    │               │               │  auto    │
    └────┬─────┘               │               └────┬─────┘
         │                     │                    │
         └─────────────────────┼────────────────────┘
                               │
                         ┌─────▼────┐
                         │  REPLY   │
                         │ HANDLER  │
                         │  (12e)   │
                         │ 8 types: │
                         │ positive │
                         │ → Voice  │
                         │ negative │
                         │ → close  │
                         │ unsub    │
                         │ → CASL   │
                         │   block  │
                         └──────────┘
```

### Wave 2 — Grow (Week 3-4)

```
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│  CONTENT  │ │  SOCIAL   │ │  VOICE    │ │ BILLING   │ │ SUPPORT   │
│  ENGINE   │ │  AGENT    │ │  AGENT    │ │  AGENT    │ │  AGENT    │
│   (9)     │ │   (10)    │ │   (26)    │ │   (17)    │ │   (18)    │
│           │ │           │ │           │ │           │ │           │
│ Editorial │ │ Syften    │ │ ⚠ WARM   │ │ Stripe WH │ │ RAG via   │
│ 3-5/week  │ │ monitoring│ │ ONLY ⚠   │ │ Reverse   │ │ pgvector  │
│           │ │           │ │           │ │ trial     │ │           │
│Programmatc│ │ 90/10     │ │ DNCL     │ │ Dunning   │ │ Bilingual │
│ SEO pages │ │ anti-ban  │ │ checked  │ │ 4-email   │ │ FR/EN     │
│ 6 templats│ │           │ │ Calling  │ │ SMS+email │ │           │
│           │ │ LinkedIn  │ │ hours    │ │ Pre-expiry│ │ Churn     │
│ /llms.txt │ │ founder   │ │ Retell AI│ │ CA taxes  │ │ detection │
│ regen     │ │ persona   │ │ $0.07/min│ │ TPS/TVQ/  │ │           │
└───────────┘ └───────────┘ └───────────┘ │ TVH      │ └───────────┘
                                          └───────────┘

┌───────────┐ ┌───────────┐ ┌───────────┐
│ REFERRAL  │ │   i18n    │ │  EMAIL    │
│  AGENT    │ │  AGENT    │ │  NURTURE  │
│   (11)    │ │   (8)     │ │   (13)    │
│           │ │           │ │           │
│ NPS ≥ 9 → │ │ FR/EN key │ │ Onboardng │
│ immediate │ │ complete? │ │ Newsletter│
│ referral  │ │ Québécois │ │ Re-engage │
│           │ │ quality?  │ │ Win-back  │
│ Double    │ │ Glossary  │ │           │
│ sided     │ │           │ │ Max 3/wk  │
│ SMS first │ │           │ │ per user  │
│ 4x higher │ │           │ │           │
└───────────┘ └───────────┘ └───────────┘
```

### Wave 3 — Optimize (Month 2+)

```
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ONBOARDING │ │  UPSELL   │ │  SOCIAL   │ │COMPETITOR │
│  AGENT    │ │  AGENT    │ │   PROOF   │ │   WATCH   │
│   (20)    │ │   (19)    │ │   (14)    │ │   (15)    │
│           │ │           │ │           │ │           │
│ Never an  │ │ >80% quota│ │ NPS ≥ 8 →│ │ Weekly    │
│ empty     │ │ >3 months │ │ request   │ │ scrape    │
│ dashboard │ │ Power     │ │ testimnl  │ │ Price     │
│           │ │ referrer  │ │ Google/   │ │ changes   │
│ Nudge at  │ │           │ │ Capterra  │ │ PH launch │
│ 24h, 72h  │ │ Max 1/mo  │ │ reviews   │ │ Funding   │
│ Aha moment│ │ per cust  │ │           │ │           │
└───────────┘ └───────────┘ └───────────┘ └───────────┘

┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│FULFILLMNT │ │  SELF-    │ │  LEGAL    │ │  DEVOPS   │ │  BUDGET   │
│   (16)    │ │REFLECTION │ │ GUARDRAIL │ │   (24)    │ │ GUARDIAN  │
│           │ │   (22)    │ │   (23)    │ │           │ │   (25)    │
│ Registry  │ │           │ │           │ │ Health    │ │           │
│ pattern   │ │ Opus:     │ │ CASL      │ │ check     │ │ $50/day   │
│ per-biz   │ │ ALL agent │ │ Privacy   │ │ every 5m  │ │ hard cap  │
│ handlers  │ │ logs +    │ │ Loi 101   │ │           │ │           │
│           │ │ ALL biz   │ │ PIPEDA    │ │ pg_dump   │ │ 80% →     │
│ Claude +  │ │ metrics   │ │ DNCL/CRTC │ │ daily     │ │ downgrade │
│ deliver   │ │           │ │ Billing   │ │ backup    │ │ model tier│
│           │ │ 8 finding │ │ patterns  │ │           │ │           │
└───────────┘ │ categories│ └───────────┘ └───────────┘ │ 90% →     │
              └───────────┘                             │ pause non │
                                                        │ essential │
┌───────────┐                                           └───────────┘
│  GROWTH   │
│  HACKER   │
│   (27)    │
│           │
│ Opus:     │
│ Non-obvius│
│ tactics   │
│           │
│ 12 tactic │
│ types     │
│ Marketplace│
│ Data-as-  │
│ marketing │
│ Template  │
│ bait      │
└───────────┘
```

---

## Database — 22 Tables

```
┌─────────────────────────────────────────────────────────────┐
│                     CORE ENTITIES                           │
│  ideas → businesses → customers, leads                      │
├─────────────────────────────────────────────────────────────┤
│                    DISTRIBUTION                             │
│  gtm_playbooks · signals · outreach_experiments             │
├─────────────────────────────────────────────────────────────┤
│                   CONTENT & MARKETING                       │
│  content · social_posts · referrals                         │
├─────────────────────────────────────────────────────────────┤
│                     OPERATIONS                              │
│  jobs · support_tickets · testimonials                      │
├─────────────────────────────────────────────────────────────┤
│                   KNOWLEDGE BASE                            │
│  knowledge_base (pgvector embeddings for RAG)               │
├─────────────────────────────────────────────────────────────┤
│                  VOICE / TELEPHONY                           │
│  voice_calls · dncl_cache · voice_scripts                   │
├─────────────────────────────────────────────────────────────┤
│                    INTELLIGENCE                             │
│  agent_logs · improvements · daily_snapshots                │
│  budget_tracking · glossary                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Orchestration** | Hatchet | Real code, Git-versioned, testable with pytest, DAG workflows, cron, retries, built-in dashboard |
| **LLM** | Claude (Opus/Sonnet/Haiku) | Auto-downgrading model tiers at budget thresholds |
| **Database** | Postgres + pgvector | CRM + RAG in one. No HubSpot needed. |
| **DNS** | Cloudflare | Free, fast, API for all record types |
| **Domains** | Namecheap | API supports .ca programmatically |
| **Hosting** | Vercel | Next.js deployment, per-business projects |
| **Code** | GitHub | One repo per business, template-based |
| **Per-biz DB** | Supabase | Auth, RLS, real-time, per-business isolation |
| **Payments** | Stripe | CAD, reverse trial, Stripe Tax for CA taxes |
| **Cold email** | Instantly.ai | Built-in warmup, rotation. Secondary domains only. |
| **Transactional email** | Resend | From Next.js business sites |
| **Voice** | Retell AI + Twilio | $0.07/min all-in. Warm calls only. |
| **Analytics** | Plausible (self-hosted) | Privacy-first, no cookie consent |
| **Monitoring** | Uptime Kuma (self-hosted) | External health checks |
| **Lead enrichment** | Apollo → Hunter → ZeroBounce | Waterfall: 80%+ match rate |
| **Audience intel** | SparkToro | Channel discovery via ICP description |
| **Community monitoring** | Syften | Keyword alerts across Reddit, FB, forums |

---

## Integration Clients

| Client | File | Purpose |
|--------|------|---------|
| Namecheap | `integrations/namecheap.py` | Domain search, purchase, NS configuration |
| Cloudflare | `integrations/cloudflare.py` | DNS zones, records, SPF/DKIM/DMARC |
| Stripe | `integrations/stripe_setup.py` | Products, prices, reverse trial subscriptions |
| Instantly | `integrations/instantly.py` | Cold email accounts, warmup, campaigns |
| Serper | `integrations/serper.py` | Google Maps lead discovery |
| Apollo | `integrations/apollo.py` | People/company enrichment |
| Hunter | `integrations/hunter.py` | Domain-based email finding |
| ZeroBounce | `integrations/zerobounce.py` | Email verification (reject catch-alls) |
| Retell AI | `integrations/retell_client.py` | Voice agent creation, outbound calls |
| Twilio | `integrations/twilio_client.py` | SMS, phone number management |
| DNCL | `integrations/dncl_client.py` | Canada Do Not Call List compliance |

---

## CEO Dashboard

Vercel-inspired dark UI. The **only** human interface — everything else is autonomous.

| Page | URL | Controls |
|------|-----|----------|
| Overview | `/` | MRR, customers, spend, agent activity, quick-trigger buttons |
| Business | `/business/{slug}` | Budget/email/voice sliders, pause toggle, Kill, Double-down, outreach approval queue |
| Agents | `/agents` | Performance table, error log, approve/reject improvement proposals |
| Budget | `/budget` | Daily costs, agent breakdown, emergency throttle/pause buttons |
| Decisions | `/decisions` | GO/KILL queue, kill alerts, outreach approval, escalations |
| Ideas | `/ideas` | Pipeline with scores, scout reports, advance/archive actions |

---

## Template Repo

A complete, buildable Next.js 15 application used as the starting point for every business the factory creates.

**Stack:** Next.js 15 · React 19 · next-intl · Tailwind CSS · Supabase Auth · Stripe · MDX blog

**Key features:**
- Bilingual FR/EN with Québécois tutoiement (next-intl, default locale `fr`)
- Pre-populated sample project on first login (never an empty dashboard)
- Reverse trial: 14-day full premium, auto-downgrade to free
- Onboarding checklist with Zeigarnik progress bar
- 3-tier pricing ($0 / $49 / $99 CAD, charm pricing)
- `/llms.txt` and `/llms-full.txt` routes for AI discoverability
- AI-friendly `robots.txt` (allows GPTBot, Claude-Web)
- Schema.org JSON-LD markup
- Plausible analytics (no cookie consent)
- Referral system with double-sided incentives
- Stripe webhook handler with signature verification
- **Every Supabase table has RLS enabled with row-level policies**

---

## Critical Design Decisions

### Warm Calls Only (§2)
AI voice calling is classified as ADAD by the CRTC. Cold AI calling = **$15,000 fine per call**. The Voice Agent only calls leads who replied to an email, filled a form, are existing customers, or requested a callback. Tested: `new`, `contacted`, and `enriched` leads are blocked.

### Reverse Trial (§4)
Day 0: full premium. Day 14: auto-downgrade to free (not cancel). Loss aversion converts higher than standard trials. Billing Agent sends 3-day warning via SMS + email.

### Never Empty Dashboard (§5)
Builder pre-populates a sample project on signup. Max 3 signup fields. Aha moment in < 2 minutes.

### Secondary Domains for Cold Email (§6)
Cold outreach from `.io`/`.co` domains only. The primary `.ca` domain stays clean for transactional email. Warmup 4-6 weeks at 5-10 emails/day before volume.

### RLS on Every Table (§12)
The Builder agent has a `verify_rls_compliance()` gate that regex-parses every `CREATE TABLE` and verifies a matching `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`. Non-compliant migrations are auto-fixed. Tests verify the template migration is compliant.

### Budget Circuit Breaker (§9)
Every agent checks budget before every Claude call. At 80%: auto-downgrade model (Opus→Sonnet→Haiku). At 100%: hard stop. Slack alert at 80%. $50/day global cap.

### Playbook-Driven Distribution (§13)
All 5 distribution sub-agents read from `gtm_playbooks`. Changing verticals = changing the playbook JSON config, not the code. Tests verify this with source code inspection.

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your API keys

# 2. Start everything
docker compose up -d

# 3. Access
# Hatchet dashboard: http://localhost:8080
# CEO dashboard:     http://localhost:9000 (admin/factory)
# Plausible:         http://localhost:8000
# Uptime Kuma:       http://localhost:3001

# 4. Run tests
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v    # 314 tests, <1 second

# 5. Seed test data (requires Postgres running)
python -m scripts.seed_test_data
```

---

## Project Structure

```
factory/
├── docker-compose.yml              # 7 services: Postgres, Hatchet, Worker, Dashboard,
│                                    #   Plausible, ClickHouse, Uptime Kuma
├── Dockerfile                       # Factory worker (Python agents)
├── Dockerfile.dashboard             # CEO Dashboard (FastAPI)
├── .env.example                     # All environment variables
├── pyproject.toml                   # Dependencies + tool config
├── SPEC.md                          # Complete specification (149K chars)
│
├── src/
│   ├── main.py                      # Hatchet worker — registers all 31 workflows
│   ├── config.py                    # pydantic-settings — loads all env vars
│   ├── db.py                        # SQLAlchemy async engine + SessionLocal
│   ├── llm.py                       # call_claude() → (text, cost_usd)
│   │
│   ├── agents/
│   │   ├── base_agent.py            # Budget circuit breaker, logging, error handling
│   │   ├── meta_orchestrator.py     # Agent 1:  CEO coordinator
│   │   ├── idea_factory.py          # Agent 2:  Idea discovery, 12-criteria scoring
│   │   ├── deep_scout.py            # Agent 3:  Market research + GTM Playbook
│   │   ├── validator.py             # Agent 4:  Landing page + ads testing
│   │   ├── brand_designer.py        # Agent 5:  Visual identity (light + full mode)
│   │   ├── domain_provisioner.py    # Agent 6:  12-step infra setup
│   │   ├── builder.py               # Agent 7:  Code gen + RLS verification + deploy
│   │   ├── i18n_agent.py            # Agent 8:  Translation QA
│   │   ├── content_engine.py        # Agent 9:  Editorial + programmatic SEO
│   │   ├── social_agent.py          # Agent 10: Community engagement + anti-ban
│   │   ├── referral_agent.py        # Agent 11: NPS-triggered double-sided referral
│   │   ├── distribution/
│   │   │   ├── lead_pipeline.py     # Agent 12a: Multi-source lead generation
│   │   │   ├── enrichment.py        # Agent 12b: Waterfall enrichment + scoring
│   │   │   ├── signal_monitor.py    # Agent 12c: Buying signal detection
│   │   │   ├── outreach.py          # Agent 12d: Tiered-autonomy cold outreach
│   │   │   └── reply_handler.py     # Agent 12e: Reply classification + routing
│   │   ├── email_nurture.py         # Agent 13: Drip campaigns (max 3/week/user)
│   │   ├── social_proof.py          # Agent 14: Testimonial collection
│   │   ├── competitor_watch.py      # Agent 15: Weekly competitor monitoring
│   │   ├── fulfillment.py           # Agent 16: Per-business service delivery
│   │   ├── billing_agent.py         # Agent 17: Stripe billing + payment recovery
│   │   ├── support_agent.py         # Agent 18: RAG customer support
│   │   ├── upsell_agent.py          # Agent 19: Usage-based upsell
│   │   ├── onboarding_agent.py      # Agent 20: Activation + nudges
│   │   ├── analytics_agent.py       # Agent 21: Metrics + kill scoring
│   │   ├── self_reflection.py       # Agent 22: Meta-cognition (Opus)
│   │   ├── legal_guardrail.py       # Agent 23: CASL/CRTC/PIPEDA compliance
│   │   ├── devops_agent.py          # Agent 24: Health checks + backups
│   │   ├── budget_guardian.py       # Agent 25: Cost throttling
│   │   ├── voice_agent.py           # Agent 26: AI voice (warm only)
│   │   └── growth_hacker.py         # Agent 27: Unconventional tactics (Opus)
│   │
│   ├── integrations/                # 11 external API clients
│   │
│   └── dashboard/                   # CEO Dashboard
│       ├── app.py                   # FastAPI + auth
│       ├── routes/                  # 7 route modules
│       └── templates/               # 8 Jinja2 templates (Vercel dark theme)
│
├── template-repo/                   # Next.js 15 template for every business
│   ├── src/app/                     # Pages, API routes, llms.txt
│   ├── src/components/              # Onboarding, pricing, reverse trial, schema.org
│   ├── src/lib/                     # Stripe, Supabase, referral utilities
│   ├── supabase/migrations/         # RLS-compliant schema
│   └── src/messages/                # en.json + fr.json (Québécois)
│
├── migrations/
│   └── 001_init.sql                 # 22 tables + indexes + pgvector
│
├── prompts/                         # System prompts for agents
│
├── scripts/
│   └── seed_test_data.py            # Sample business + leads for testing
│
└── tests/                           # 314 tests, <1 second
    ├── test_meta.py
    ├── test_idea_factory.py
    ├── test_deep_scout.py
    ├── test_builder.py              # RLS compliance tests
    ├── test_brand_designer.py
    ├── test_domain_provisioner.py   # Cold email domain separation tests
    ├── test_analytics.py            # Kill score formula tests
    ├── test_distribution.py         # Lead scoring, anti-ban, tiered autonomy
    ├── test_content_social_referral.py
    ├── test_billing_support_voice.py # Warm-calls-only compliance tests
    ├── test_dashboard.py            # Auth, routes, critical controls
    └── test_integration_lifecycle.py # Full lifecycle simulation
```

---

## License

Private. See SPEC.md for the complete specification.

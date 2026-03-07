# AUTONOMOUS BUSINESS FACTORY — Complete Technical Specification

## For: Cursor AI / Claude Code
## Stack: Hatchet + Python + Postgres + Docker
## Goal: Build a system of 27 AI agents that autonomously discover, validate, build, market, sell, growth-hack, and operate micro-SaaS businesses in Canada

---

## ⚠️ CRITICAL DESIGN CHANGES (READ FIRST — overrides anything below)

These learnings come from analyzing 1,200+ failed micro-SaaS businesses and production multi-agent systems. They override or supplement the detailed specs below.

### 1. PHASED AGENT LAUNCH — NOT 27 AT ONCE

92% of micro-SaaS fail within 18 months, and 40% of multi-agent pilots fail within 6 months. Do NOT build all 27 agents before launching. Launch in 3 waves:

**WAVE 1 (Days 1-10) — Ship and sell. Only 7 agents:**
- Meta Orchestrator (coordinator)
- Idea Factory + Deep Scout (find & validate ideas)
- Brand Designer (light mode only — colors + name)
- Domain Provisioner (infra setup)
- Builder (code the MVP)
- Outbound Sales (cold email — THE most important agent)
- Analytics & Kill (measure everything)

**WAVE 2 (Week 3-4, after first paying customer) — Grow:**
- Content Engine + GEO (SEO + LLM optimization)
- Social Agent (Reddit, LinkedIn)
- Voice Agent (warm calls only — see below)
- Billing Agent (dunning, payment recovery)
- Support Agent (RAG)

**WAVE 3 (Month 2+, after 10+ customers) — Optimize:**
- All remaining agents: Referral, Nurture, Upsell, Onboarding, Social Proof, Competitor Watch, Growth Hacker, Self-Reflection, Legal Guardrail, i18n, DevOps, Budget Guardian

**Why:** Every agent you build before having customers is waste. The Sales agent and Builder are 10x more important than the Self-Reflection agent on day 1. Get revenue first, optimize later.

### 2. VOICE CALLING — WARM ONLY, NOT COLD

The research is clear: CRTC classifies AI voice calling as ADAD (Automated Dialing-Announcing Device), which requires EXPRESS CONSENT before calling. Cold AI calling to new Canadian prospects = $15,000 fine per call.

**Restructured voice strategy:**
- AI voice (Retell) is used ONLY for:
  - Leads who replied to a cold email (they've engaged = implied consent for follow-up)
  - Leads who signed up on landing page (express consent via form)
  - Existing customers (support, payment follow-up)
  - Leads who opted in to a callback ("Want us to call you? Leave your number")
- TRUE cold outreach stays email-only (CASL allows B2B cold email with implied consent via conspicuous publication)
- The Voice Agent's `check_compliance` step must verify consent type BEFORE every call

This is still hugely valuable — a warm AI call to someone who replied "sounds interesting" to a cold email converts 5-10x better than another email.

### 3. DISTRIBUTION > BUILDING — REORDER EVERYTHING

68% of failed SaaS built products nobody wanted. Your factory's marketing agents are MORE important than its coding agents.

**New priority order for agent development time:**
1. Outbound Sales (cold email sequences) — revenue on day 1
2. Builder (MVP) — just enough to deliver value
3. Content Engine + GEO — compounds over time, start early
4. Growth Hacker — non-obvious channels
5. Everything else

**Missing high-ROI channel — add to spec:**
**Ecosystem/marketplace distribution.** Shopify App Store drove 32% of new merchant growth. QuickBooks App Store, Xero Marketplace, Jobber integrations. For each business, the Builder should create a basic integration with the #1 tool the ICP already uses, and list it on their marketplace. This is FREE acquisition inside existing workflows. Add this as a step in the Builder and Growth Hacker agents.

### 4. REVERSE TRIAL MODEL — NOT STANDARD FREE TRIAL

Standard freemium converts <5%. Standard free trial converts ~15%. Reverse trial converts significantly higher because of loss aversion (losing something is 2x more painful than gaining it).

**How it works for every business the factory builds:**
- Day 0: User gets FULL premium access (all features, no limits)
- Day 14: Automatically downgrade to free tier (limited features)
- User has experienced premium, now feels the loss → higher conversion to paid
- The free tier should be genuinely useful (not crippled) but make the premium value obvious

**Implementation:** Stripe subscription starts as "trial" with all features. At day 14, auto-switch to free plan. Upgrade CTA shows what they're losing. The Billing Agent handles this transition.

### 5. ONBOARDING — PRE-POPULATE, DON'T START EMPTY

77% of SaaS users disappear in 3 days. Trades workers are time-poor and mobile-first. They will NOT configure 15 settings on an empty dashboard.

**Rules for the Builder agent when building each MVP:**
- NEVER show an empty dashboard after signup
- Pre-populate a sample project using AI (sample quote, sample invoice, sample audit) so the user sees the product WORKING before they configure anything
- Signup form: MAX 3 fields (name, email, phone). Skip email verification.
- First "aha moment" must happen within 2 minutes, not 2 days
- Onboarding checklist with progress bar (Zeigarnik effect)
- SMS notifications alongside email (trades workers check texts, not email)
- Detect language from signup (QC area code → FR, else → EN)

### 6. COLD EMAIL RULES — 2026 PRACTICES

Cold email deliverability has changed dramatically. The Sales Agent must follow these:
- Messages UNDER 80 words. Single CTA. No links in email 1 (triggers spam filters).
- No images, no attachments, no HTML formatting in cold emails
- SECONDARY sending domains (never send cold email from the main business domain)
  - Example: if business is toituro.ca, cold email from toituro.io or toituro.co
  - Protects the main domain's reputation
- Warm up at 5-10 emails/day for 4-6 weeks (not 14 days as previously stated)
- Tuesday-Wednesday = peak reply days
- SPF + DKIM + DMARC mandatory on every sending domain
- Track reply rate, not open rate (open tracking triggers spam filters in 2026)
- CASL compliance: B2B cold email is legal IF the email is conspicuously published AND the message is relevant to their business role. Log the source of every email address.

### 7. PAYMENT RECOVERY — STOP THE SILENT REVENUE LEAK

Involuntary churn (failed payments) = up to 40% of total churn. Up to 70% is recoverable.

**Add to Billing Agent:**
- Enable Stripe Smart Retries (ML-optimized retry scheduling) — free, enable in Stripe dashboard
- Enable Stripe Card Account Updater (auto-updates expired cards via card networks) — reduces hard declines by 30-50%
- Enable Stripe Adaptive Acceptance
- Pre-dunning: email customers 30/15/7 days BEFORE card expiry ("Your card ending in 4242 expires next month. Update it here →")
- Failed payment wall: when payment fails, show an in-app banner restricting features until payment updates (adds ~3% to recovery)
- Multi-channel dunning: email + in-app notification + SMS (not just email)

### 8. PRICING — WHAT WORKS FOR TRADES/CONTRACTORS

- FLAT-RATE pricing, NOT per-seat. Trades teams fluctuate seasonally. Per-seat = friction.
- Price in CAD always (a $49 USD tool feels like $67 CAD — FX kills conversion)
- Charm pricing: $49/mo not $50/mo (24% conversion lift with SMBs)
- Annual billing at 16-20% discount (2 months free) — reduces churn 20-30%
- Three tiers with the middle as the "recommended" (decoy effect)
- Value messaging: "Save 4 hours per quote" not "AI-powered estimation"

### 9. COST CIRCUIT BREAKERS — PREVENT RUNAWAY API BILLS

A 3-agent workflow costing $5 in demos can generate $18,000+/month at scale.

**Add to every agent (in the base class):**
```python
# Every agent checks this BEFORE making any Claude API call
async def check_budget(self, agent_name: str, estimated_cost: float):
    daily_spent = db.query("SELECT SUM(cost_usd) FROM agent_logs WHERE agent_name = :name AND created_at > CURRENT_DATE", {"name": agent_name})
    if daily_spent + estimated_cost > AGENT_DAILY_LIMIT:
        # Try downgrading model tier
        if self.model == "opus": self.model = "sonnet"
        elif self.model == "sonnet": self.model = "haiku"
        else:
            raise BudgetExceededError(f"{agent_name} daily budget exhausted")
```
- Per-agent daily limits (configurable via dashboard)
- Auto-downgrade model tier when approaching limit
- Hard stop when limit reached (no exceptions)
- Alert on Slack when any agent hits 80% of daily budget

### 10. DEFENSIBILITY — ENCODE DOMAIN EXPERTISE, NOT JUST AI

In 2026, anyone can build what your factory builds with Cursor in a weekend. Features are NOT a moat. Your moat must be:

**Data flywheel:** Every quote generated in Quote OS, every collection in AR Collections → aggregated anonymized data that improves the AI for ALL users. "Powered by 10,000+ real estimates from Quebec contractors." New entrants start with zero data.

**Vertical domain logic:** The Builder must encode business logic that only insiders know:
- Quote OS: Change order disputes require cross-referencing original bid documents against daily field reports. Seasonal pricing adjustments for Quebec (winter surcharges, spring demand spikes).
- AR Collections: Quebec-specific payment culture (net 45 is standard, not net 30). Construction holdback rules (10% withheld for 55 days under Quebec Civil Code).
- The Scout Report must capture this domain knowledge and the Builder must implement it.

**Switching costs:** Every month a contractor uses Quote OS, they build a history of quotes, client contacts, pricing data. Leaving means losing all of that. Design for data accumulation.

### 11. SR&ED TAX CREDITS — FREE MONEY

Canada's Scientific Research & Experimental Development (SR&ED) program offers a 35% refundable tax credit on qualifying R&D expenses for Canadian-controlled private corporations. Your AI agent development almost certainly qualifies.

**Action:** Track all development hours and API costs from day 1. File SR&ED annually. Could recover 35% of your development costs. Quebec stacks an additional 14-30% provincial credit. Combined, potentially 50%+ of eligible expenses come back as cash.

Add a note in the Analytics Agent to track development costs separately for SR&ED reporting.

### 12. SUPABASE SECURITY — THE THING THAT WILL BITE YOU

67% of SaaS breaches trace to misconfigurations. The most dangerous with Supabase:

**Row Level Security (RLS) is DISABLED by default on new tables.** Every table without RLS is publicly accessible via the anon key. The Builder MUST add `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and proper policies to EVERY `CREATE TABLE` in EVERY migration. This is non-negotiable.

**Multi-tenant data isolation:** Since we run multiple businesses on shared Supabase instances, every query must scope by `business_id`. RLS policies must enforce this at the database level, not just the application level.

**Regenerate ALL default secrets** from the Supabase example .env file before deploying anything.

## PROJECT OVERVIEW

This is a self-hosted autonomous business factory. It discovers SaaS ideas that work in the US but don't exist in Canada, validates them with real ads, builds MVPs, markets them for $0 (organic), sells them via cold email AND AI cold calling, and operates them — all with minimal human intervention (~2-3h/week of CEO oversight).

The system runs on a single Hetzner VPS with Docker. It uses Hatchet as the workflow orchestration engine (durable execution, retries, DAG workflows, monitoring dashboard). Each "agent" is a Python module with Hatchet workflow definitions. Agents communicate via Postgres (shared state) and Hatchet workflow triggers. Voice calling is handled by Retell AI (voice) + Twilio (telephony), with strict CRTC/DNCL compliance built into every outbound call.

**Key stack decisions (and why):**
- **Hatchet** (not n8n or Temporal): real code, Git-versioned, testable, no determinism constraint, built-in dashboard
- **Namecheap** for domain purchase (API supports .ca + .com programmatically) → **Cloudflare** for DNS (CF Registrar has no purchase API for non-Enterprise)
- **Sendgrid** for transactional email (receipts, onboarding, dunning) — **Instantly.ai** for cold email (built-in warmup, rotation, deliverability tracking). Do NOT use Sendgrid for cold outreach — it will destroy your domain reputation.
- **Postgres** as the CRM — NO HubSpot. The `leads` and `customers` tables ARE your CRM. Adding HubSpot is unnecessary complexity. If you need a UI later, build a simple admin dashboard.
- **Plausible Analytics** (self-hosted) instead of GA4 — lighter, privacy-first, no cookie consent banner needed, and you own the data. Add to Docker Compose.
- **pgvector** extension on existing Postgres for RAG (Support Agent) instead of separate Qdrant — one less service to manage
- **Hetzner Object Storage** for backups instead of S3/Backblaze — same datacenter, S3-compatible API, cheaper
- **Uptime Kuma** (self-hosted) for external health monitoring — add to Docker Compose
- **Retell AI** for voice ($0.07/min all-in) instead of Vapi ($0.18-0.33 effective)
- **Resend** for transactional email from Next.js business sites (better DX than Sendgrid for Next.js) — Sendgrid stays for bulk/sequences from the Python agents

**Why Hatchet, not n8n or Temporal:**
- Unlike n8n: real code, version-controlled in Git, testable with pytest, no visual spaghetti at 100+ workflows
- Unlike Temporal: no determinism constraint, just normal Python, simpler self-hosting (Hatchet engine + Postgres only), built-in dashboard
- Hatchet handles: durable execution, retries with backoff, DAG workflows, cron scheduling, concurrency control, observability

### 14. EVENT-DRIVEN PIPELINE — NO WAITING

The pipeline from idea to live business must be EVENT-DRIVEN, not cron-driven. Every step cascades IMMEDIATELY to the next without waiting for the Meta Orchestrator's daily cron.

**The cascade:**
```
Idea Factory finds idea (score ≥ 7)
    → IMMEDIATELY triggers Deep Scout (parallel: 3 ideas = 3 scouts running simultaneously)
        → Scout says GO → IMMEDIATELY triggers Validator (Brand light + landing page + ads)
            → 7 days of ads (the ONLY forced wait in the pipeline)
            → Signup > 5% (STRONG GO) → auto-cascades to Brand full → Domain → Builder
            → Signup 3-5% (GO) → auto-cascades same way
            → Signup 1-3% → notifies Dashboard for human GO/KILL decision
            → Signup < 1% → auto-killed
                → Builder deploys → IMMEDIATELY triggers Distribution Engine
                    → Lead Pipeline finds leads → Enrichment → Outreach starts
```

**Timeline: idea to first cold email sent = ~10 days** (7 days of validation + 3 days of build/deploy). Without the validation wait, a manually approved idea goes from GO to selling in ~48 hours.

**Parallelism:** The factory can run 5+ pipelines simultaneously:
- Business A: live, selling, 50 emails/day
- Business B: in validation (day 4 of 7)
- Ideas C, D, E: being scouted by 3 parallel Deep Scout runs
- Idea F: scoring in Idea Factory

Hatchet handles all concurrency. Budget Guardian enforces the total daily spend cap across all parallel workflows. If budget is tight, it pauses lower-priority pipelines (new ideas) to protect revenue-generating ones (live businesses).

**The Meta Orchestrator's daily 6AM cron is OVERSIGHT ONLY** — reviewing metrics, reallocating budgets, flagging problems. It does NOT gate pipeline advancement. Events do that.

### 13. UNIVERSAL DISTRIBUTION ARCHITECTURE — THE MOST IMPORTANT SECTION

The distribution system must sell ANY business the factory creates, not just one. It takes 5 inputs (ICP, product, value prop, pricing, competitors) and autonomously figures out channels, finds leads, and runs outreach. Here's how:

**A) GTM PLAYBOOK CONFIG (one per business, generated by Deep Scout, consumed by all sales/growth agents):**
```yaml
# Stored in DB table `gtm_playbooks`, generated by Deep Scout, editable via Dashboard
business_id: 1
icp:
  naics_codes: ["238160"]  # Roofing contractors
  company_size: "1-25 employees"
  decision_maker_titles: ["owner", "président", "estimateur"]
  geo: "QC"  # Province code
  language: "fr"
  tech_signals: ["no_website", "facebook_only", "spreadsheet_user"]
  pain_keywords: ["estimation longue", "soumission perdue", "calcul erreur"]

channels:
  primary: "cold_email"  # Determined by Bullseye scoring
  secondary: "facebook_groups"
  tertiary: "association_partnership"
  ranked_channels:  # ICE scored (Impact × Confidence × Ease)
    - {channel: "cold_email", ice: 216, status: "active"}
    - {channel: "facebook_groups", ice: 180, status: "active"}
    - {channel: "association", ice: 168, status: "pending_outreach"}
    - {channel: "reddit", ice: 72, status: "deprioritized"}

lead_sources:
  - {type: "google_maps", query: "couvreur toiture", geo: "QC", priority: 1}
  - {type: "rbq_registry", licence_type: "couvreur", priority: 2}
  - {type: "association_directory", org: "AMCQ", url: "amcq.qc.ca/membres/", priority: 3}
  - {type: "req_registry", naics: "238160", priority: 4}

associations:
  - {name: "AMCQ", url: "amcq.qc.ca", type: "direct_niche", partnership_status: "not_contacted"}
  - {name: "APCHQ", url: "apchq.com", type: "umbrella", partnership_status: "not_contacted"}

ecosystems:
  - {platform: "QuickBooks", marketplace: "apps.intuit.com", integration_type: "export", priority: 1}
  - {platform: "Acomba", marketplace: null, integration_type: "csv_import", priority: 2}

messaging:
  value_prop_fr: "Créez des soumissions professionnelles en 5 minutes, pas 2 heures"
  value_prop_en: "Create professional quotes in 5 minutes, not 2 hours"
  pain_points: ["manual estimation takes too long", "errors cost money", "unprofessional-looking quotes"]
  proof_points: ["X devis créés", "Y heures économisées"]
  tone: "direct, tutoiement, québécois authentique"
  frameworks: ["pain_agitate_solve", "before_after_bridge"]

outreach:
  email_templates: 4  # Number of emails in sequence
  sequence_days: [0, 3, 7, 12]
  max_daily_emails: 50  # Start low, scale after warmup
  voice_trigger: "replied_positive"  # When to trigger warm call
  cadence: "email → email → email+loom → breakup"

signals:  # Buying signals to monitor for this ICP
  - {type: "new_business_registration", source: "req_registry", weight: 9}
  - {type: "building_permit_issued", source: "municipal_data", weight: 8}
  - {type: "competitor_complaint", source: "google_reviews", weight: 7}
  - {type: "hiring_estimator", source: "indeed_scrape", weight: 6}
  - {type: "website_visit", source: "plausible", weight: 10}

referral:
  incentive: "1_month_free"  # Both sides get 1 month free
  ask_trigger: "nps_9_or_10"
  program_type: "double_sided"
```

**B) THE SALES AGENT IS 5 SUB-AGENTS, not 1 monolithic agent:**
1. **Lead Pipeline Agent** — finds leads from configured sources (Google Maps, RBQ, REQ, associations, etc.)
2. **Enrichment Agent** — waterfall enrichment: Apollo → Hunter → Dropcontact → website scrape. Verifies emails. Scores leads.
3. **Signal Monitor Agent** — watches for buying signals (new registrations, job posts, competitor complaints, website visits) and pushes hot leads to top of queue
4. **Outreach Agent** — generates personalized messages from playbook config, runs multi-channel sequences via Instantly (email) + LinkedIn + Voice
5. **Reply Handler Agent** — classifies replies (positive/negative/question/OOO), routes positive replies to Voice Agent or demo booking, handles objections

**C) TIERED AUTONOMY (shadow mode first):**
- **Week 1-2:** All outreach messages go to Slack for human review before sending. Agent drafts, human approves.
- **Week 3-4:** Agent sends autonomously for low-value leads (<$100 ACV expected). Human reviews high-value.
- **Month 2+:** Full autonomy for validated ICP + messaging combos. Human only reviews new verticals or failing sequences (reply rate < 2%).

**D) CHANNEL DISCOVERY is automated via SparkToro + Claude:**
Deep Scout queries SparkToro's audience intelligence with the ICP description → gets back which websites, social platforms, podcasts, YouTube channels, subreddits, and Facebook groups the audience engages with → Claude scores each channel using ICE (Impact × Confidence × Ease) → top 3 go into the playbook config. This replaces hardcoded channel assumptions.

**E) CANADIAN LEAD SOURCES (free/cheap, built into Lead Pipeline Agent):**
- **RBQ Open Data** — 50,000+ active contractor licences in Quebec, free (Creative Commons 4.0). Includes name, address, NEQ, licence type.
- **REQ** (Registraire des entreprises du Québec) — all registered Quebec businesses. Bulk extract $134 or per-lookup via API.
- **Federal Corporation API** — 1M+ federally incorporated entities, free real-time API via Canada's API Store.
- **Google Maps/Places API** — any local business, $200/month free tier, Serper Maps API at $0.20/1000 leads as cheaper alternative.
- **Provincial professional orders** (OPQ) — 46 orders, each with member directories (accountants, architects, engineers, etc.)
- **Open data portals** — building permits, new business registrations, industry-specific datasets

**F) WATERFALL ENRICHMENT (not single-source):**
Single-source email finding hits ~40-50% match rate. Waterfall across 3-4 providers hits 80%+. The Enrichment Agent runs: Apollo → Hunter → Dropcontact → website contact page scrape → LinkedIn profile extraction. Each step only runs if the previous one failed. ZeroBounce verifies before sending.

**G) SIGNAL-BASED SELLING (5.2x higher reply rates):**
Instead of blasting cold emails to a static list, the Signal Monitor Agent watches for buying signals specific to each business's ICP and pushes triggered leads to the top of the outreach queue with signal-specific personalization. Signal-based outreach achieves 15-25% reply rates vs 3% for generic cold email. Key signals:
- New business registrations (REQ) → "Congrats on launching [business]. Many new couvreurs use [product] to..."
- Job postings for roles the product replaces → "I noticed you're hiring an estimator. What if..."
- Competitor negative reviews → "I saw [company] struggling with [pain]. We solve this differently..."
- Website visitors (Plausible API) → priority outreach within 24h
- Industry regulation changes → "New OQLF rules require [X]. Here's how to comply instantly..."

---

## DIRECTORY STRUCTURE

```
factory/
├── docker-compose.yml
├── .env
├── pyproject.toml
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py                    # Hatchet client init + worker startup
│   ├── config.py                  # Settings: reads secrets from DB (encrypted), falls back to .env
│   ├── db.py                      # SQLAlchemy models + Postgres connection
│   ├── llm.py                     # Claude API wrapper (Opus/Sonnet/Haiku selector)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py            # Base class: budget circuit breaker, logging, error handling
│   │   ├── meta_orchestrator.py   # Agent 1: CEO coordinator
│   │   ├── idea_factory.py        # Agent 2: Idea discovery & scoring
│   │   ├── deep_scout.py          # Agent 3: Deep market research
│   │   ├── validator.py           # Agent 4: Landing page + ads testing
│   │   ├── brand_designer.py      # Agent 5: Visual identity & branding
│   │   ├── domain_provisioner.py  # Agent 6: Domain + infra setup
│   │   ├── builder.py             # Agent 7: MVP code generation & deploy
│   │   ├── i18n_agent.py          # Agent 8: Translation & localization QA
│   │   ├── content_engine.py      # Agent 9: SEO blog content ($0 marketing)
│   │   ├── social_agent.py        # Agent 10: Reddit, LinkedIn, FB groups
│   │   ├── referral_agent.py      # Agent 11: Referral program management
│   │   ├── distribution/            # Agent 12: Universal Distribution Engine (5 sub-agents)
│   │   │   ├── __init__.py
│   │   │   ├── lead_pipeline.py     # 12a: Multi-source lead generation
│   │   │   ├── enrichment.py        # 12b: Waterfall enrichment + scoring
│   │   │   ├── signal_monitor.py    # 12c: Buying signal detection
│   │   │   ├── outreach.py          # 12d: Multi-channel personalized outreach
│   │   │   └── reply_handler.py     # 12e: Reply classification + routing
│   │   ├── email_nurture.py       # Agent 13: Drip campaigns & newsletters
│   │   ├── social_proof.py        # Agent 14: Testimonials & case studies
│   │   ├── competitor_watch.py    # Agent 15: Competitor monitoring
│   │   ├── fulfillment.py         # Agent 16: Per-business service delivery
│   │   ├── billing_agent.py       # Agent 17: Stripe billing & dunning
│   │   ├── support_agent.py       # Agent 18: Customer support (RAG)
│   │   ├── upsell_agent.py        # Agent 19: Upsell & cross-sell
│   │   ├── onboarding_agent.py    # Agent 20: New client activation
│   │   ├── analytics_agent.py     # Agent 21: Metrics & kill scoring
│   │   ├── self_reflection.py     # Agent 22: Meta-cognition & improvement
│   │   ├── legal_guardrail.py     # Agent 23: Compliance scanning
│   │   ├── devops_agent.py        # Agent 24: Health checks & backups (bonus)
│   │   ├── budget_guardian.py     # Agent 25: API cost tracking & throttling (bonus)
│   │   ├── voice_agent.py         # Agent 26: AI cold calling & voice support (Retell/Vapi)
│   │   └── growth_hacker.py       # Agent 27: Unconventional acquisition tactics
│   │   # NOTE: Agent 28 (GEO/LLM Optimizer) is part of the Content Engine, not a separate file.
│   │   # Its logic lives in content_engine.py as additional steps.
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── app.py                 # CEO Dashboard — FastAPI + HTMX (or Next.js)
│   │   ├── routes/
│   │   │   ├── overview.py        # Global factory metrics
│   │   │   ├── businesses.py      # Per-business deep dive
│   │   │   ├── agents.py          # Agent performance & logs
│   │   │   ├── budget.py          # Budget controls & allocation
│   │   │   └── decisions.py       # Kill/go/scale controls
│   │   └── templates/             # Jinja2 templates (if HTMX) or React components
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── anthropic_client.py    # Claude API (Opus, Sonnet, Haiku)
│   │   ├── stripe_client.py       # Stripe Connect + billing
│   │   ├── namecheap_client.py    # Domain search + purchase (API supports .ca)
│   │   ├── cloudflare_client.py   # DNS management
│   │   ├── vercel_client.py       # Project creation + deployment
│   │   ├── github_client.py       # Repo creation + code push
│   │   ├── supabase_client.py     # Project creation + DB management
│   │   ├── sendgrid_client.py     # Email sending + templates
│   │   ├── google_ads_client.py   # Ad campaign management
│   │   ├── meta_ads_client.py     # Facebook/Instagram ads
│   │   ├── google_search.py       # Search Console + Indexing API
│   │   ├── reddit_client.py       # Reddit API for posting/commenting
│   │   ├── instantly_client.py    # Cold email sending + warmup (NOT Sendgrid for cold)
│   │   ├── plausible_client.py    # Self-hosted analytics API
│   │   ├── slack_client.py        # Alert notifications
│   │   ├── retell_client.py       # Retell AI voice agent API (outbound calls)
│   │   ├── twilio_client.py       # Twilio telephony (phone numbers + PSTN)
│   │   ├── dncl_client.py         # Canada National DNCL registry lookup
│   │   └── scraper.py             # Generic HTTP scraping utilities
│   ├── prompts/
│   │   ├── meta_orchestrator.txt
│   │   ├── idea_factory.txt
│   │   ├── deep_scout.txt
│   │   ├── validator.txt
│   │   ├── brand_designer.txt
│   │   ├── builder.txt
│   │   ├── content_engine.txt
│   │   ├── outbound_sales.txt
│   │   ├── support_agent.txt
│   │   ├── self_reflection.txt
│   │   ├── voice_agent.txt
│   │   └── ... (one per agent)
│   └── templates/
│       ├── landing_page.html      # Validation landing page template (bilingual)
│       ├── email_welcome_fr.html
│       ├── email_welcome_en.html
│       ├── email_dunning_1_fr.html
│       ├── email_dunning_1_en.html
│       └── ... (all email templates bilingual)
├── tests/
│   ├── test_idea_factory.py
│   ├── test_deep_scout.py
│   └── ...
├── migrations/
│   └── 001_initial_schema.sql
└── scripts/
    ├── seed_data.py               # Initial data for testing
    └── backup.sh                  # Database backup script
```

---

## DOCKER COMPOSE

```yaml
version: '3.8'

services:
  # ── Postgres with pgvector (shared by Hatchet + Factory + RAG) ──
  postgres:
    image: pgvector/pgvector:pg16
    restart: always
    environment:
      POSTGRES_USER: factory
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: factory
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U factory"]
      interval: 5s
      timeout: 5s
      retries: 10

  # ── Hatchet Engine (workflow orchestration) ──
  hatchet-engine:
    image: ghcr.io/hatchet-dev/hatchet/hatchet-engine:latest
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://factory:${POSTGRES_PASSWORD}@postgres:5432/factory
      SERVER_AUTH_COOKIE_SECRETS: ${HATCHET_COOKIE_SECRET}
      SERVER_AUTH_COOKIE_DOMAIN: localhost
      SERVER_AUTH_COOKIE_INSECURE: "true"
      SERVER_GRPC_BIND_ADDRESS: "0.0.0.0"
      SERVER_GRPC_PORT: "7070"
      SERVER_GRPC_BROADCAST_ADDRESS: "hatchet-engine:7070"
    ports:
      - "8080:8080"   # Dashboard UI
      - "7070:7070"   # gRPC for workers

  # ── Factory Worker (our Python agents) ──
  factory-worker:
    build: .
    restart: always
    depends_on:
      - hatchet-engine
      - postgres
    environment:
      HATCHET_CLIENT_HOST: hatchet-engine:7070
      HATCHET_CLIENT_TLS_STRATEGY: none
      DATABASE_URL: postgres://factory:${POSTGRES_PASSWORD}@postgres:5432/factory
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}
      NAMECHEAP_API_KEY: ${NAMECHEAP_API_KEY}
      NAMECHEAP_API_USER: ${NAMECHEAP_API_USER}
      CLOUDFLARE_API_TOKEN: ${CLOUDFLARE_API_TOKEN}
      VERCEL_TOKEN: ${VERCEL_TOKEN}
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      SUPABASE_ACCESS_TOKEN: ${SUPABASE_ACCESS_TOKEN}
      SENDGRID_API_KEY: ${SENDGRID_API_KEY}
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
      GOOGLE_ADS_DEVELOPER_TOKEN: ${GOOGLE_ADS_DEVELOPER_TOKEN}
      META_ADS_ACCESS_TOKEN: ${META_ADS_ACCESS_TOKEN}
      INSTANTLY_API_KEY: ${INSTANTLY_API_KEY}
      REDDIT_CLIENT_ID: ${REDDIT_CLIENT_ID}
      REDDIT_CLIENT_SECRET: ${REDDIT_CLIENT_SECRET}
    volumes:
      - ./src:/app/src
      - ./prompts:/app/prompts

  # ── Plausible Analytics (self-hosted, privacy-first, no cookie consent needed) ──
  plausible:
    image: ghcr.io/plausible/community-edition:latest
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgres://factory:${POSTGRES_PASSWORD}@postgres:5432/plausible
      BASE_URL: https://analytics.factorylabs.ca
      SECRET_KEY_BASE: ${PLAUSIBLE_SECRET}

  # ── Uptime Kuma (self-hosted uptime monitoring with alerts) ──
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    restart: always
    ports:
      - "3001:3001"
    volumes:
      - uptime_kuma_data:/app/data

volumes:
  postgres_data:
  uptime_kuma_data:
```

---

## DATABASE SCHEMA (Postgres)

This is the shared state that ALL agents read from and write to. Run this as migration 001.

```sql
-- ═══ EXTENSIONS ═══
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector for RAG (Support Agent knowledge base)

-- ═══ CORE ENTITIES ═══

CREATE TABLE ideas (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    niche TEXT,
    us_equivalent TEXT,
    us_equivalent_url TEXT,
    ca_gap_analysis TEXT,
    score NUMERIC(3,1),
    scoring_details JSONB,  -- {criterion: score} for all 12 criteria
    status TEXT DEFAULT 'new' CHECK (status IN ('new','scouting','scouted','validating','validated','approved','building','live','killed')),
    scout_report TEXT,       -- Markdown
    validation_metrics JSONB,
    kill_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE businesses (
    id SERIAL PRIMARY KEY,
    idea_id INT REFERENCES ideas(id),
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    domain TEXT,
    niche TEXT,
    status TEXT DEFAULT 'setup' CHECK (status IN ('setup','building','pre_launch','live','paused','killed')),
    -- Infra
    stripe_account_id TEXT,
    vercel_project_id TEXT,
    github_repo TEXT,
    supabase_project_id TEXT,
    supabase_url TEXT,
    supabase_anon_key TEXT,
    cloudflare_zone_id TEXT,
    sendgrid_domain_verified BOOLEAN DEFAULT FALSE,
    ga4_measurement_id TEXT,
    search_console_verified BOOLEAN DEFAULT FALSE,
    -- Brand
    brand_kit JSONB,         -- {colors, typography, tone, mood_board, ui_patterns, canadian_elements}
    -- Config
    pricing JSONB,           -- [{name, price_cad, stripe_price_id, features}]
    icp JSONB,               -- {role, company_size, pain_points, channels}
    config JSONB,            -- Business-specific config
    -- Metrics (denormalized for quick access)
    mrr NUMERIC(10,2) DEFAULT 0,
    customers_count INT DEFAULT 0,
    kill_score NUMERIC(5,2),
    -- Timestamps
    launched_at TIMESTAMPTZ,
    killed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    name TEXT,
    email TEXT NOT NULL,
    company TEXT,
    language TEXT DEFAULT 'fr' CHECK (language IN ('fr','en')),
    province TEXT,            -- For tax calculation
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    plan TEXT,
    mrr NUMERIC(8,2) DEFAULT 0,
    status TEXT DEFAULT 'trial' CHECK (status IN ('trial','active','past_due','churned','paused')),
    referral_code TEXT UNIQUE,
    referred_by_customer_id INT REFERENCES customers(id),
    aha_moment_reached BOOLEAN DEFAULT FALSE,
    aha_moment_at TIMESTAMPTZ,
    onboarding_step INT DEFAULT 0,
    nps_score INT,
    last_active_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    name TEXT,
    email TEXT,
    company TEXT,
    phone TEXT,
    source TEXT CHECK (source IN ('google_maps','rbq_registry','req_registry','federal_corp','association_directory','industry_directory','cold_email','reddit','seo','referral','ads','linkedin','facebook_group','product_hunt','organic','website_visitor','signal','other')),
    source_url TEXT,              -- CASL: where we found this email (for implied consent proof)
    consent_type TEXT CHECK (consent_type IN ('conspicuous_publication','business_relationship','express','inquiry','none')),
    status TEXT DEFAULT 'new' CHECK (status IN ('new','enriching','enriched','contacted','replied','booked','trial','converted','lost','unsubscribed')),
    language TEXT DEFAULT 'fr',
    province TEXT,
    score INT DEFAULT 0,          -- 0-100 lead score from Enrichment Agent
    enrichment_data JSONB,        -- Company size, website, tech stack, enrichment sources used
    enrichment_sources TEXT[],    -- ['apollo','hunter','website_scrape'] — which providers found data
    signal_type TEXT,             -- Most recent buying signal type
    signal_date TIMESTAMPTZ,     -- When signal was detected
    signal_data JSONB,           -- Signal-specific data (e.g., permit number, job posting URL)
    notes TEXT,
    sequence_step INT DEFAULT 0,
    sequence_channel TEXT DEFAULT 'email',  -- Current channel in multi-channel sequence
    last_contacted_at TIMESTAMPTZ,
    replied_at TIMESTAMPTZ,      -- When they first replied (for warm call timing)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ GTM PLAYBOOKS (one per business, generated by Deep Scout, consumed by all distribution agents) ═══

CREATE TABLE gtm_playbooks (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) UNIQUE,
    config JSONB NOT NULL,       -- Full playbook YAML converted to JSON (see §13 for schema)
    version INT DEFAULT 1,       -- Increment on every update (for audit trail)
    last_updated_by TEXT,        -- 'deep_scout', 'self_reflection', 'human'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ BUYING SIGNALS ═══

CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    lead_id INT REFERENCES leads(id),  -- NULL if signal detected before lead exists
    signal_type TEXT NOT NULL,    -- 'new_business_registration', 'building_permit', 'competitor_complaint', 'job_posting', 'website_visit', 'regulation_change'
    source TEXT,                  -- 'req_registry', 'municipal_data', 'google_reviews', 'indeed', 'plausible', etc.
    data JSONB,                  -- Signal-specific data
    weight INT,                  -- Signal strength (from playbook config)
    actioned BOOLEAN DEFAULT FALSE,  -- Has this signal been used in outreach?
    actioned_at TIMESTAMPTZ,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ OUTREACH EXPERIMENTS (A/B testing for message optimization) ═══

CREATE TABLE outreach_experiments (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    experiment_name TEXT,         -- 'subject_line_v1_vs_v2', 'opening_pain_vs_timeline'
    variant_a TEXT,               -- Message variant A
    variant_b TEXT,               -- Message variant B
    sends_a INT DEFAULT 0,
    sends_b INT DEFAULT 0,
    replies_a INT DEFAULT 0,
    replies_b INT DEFAULT 0,
    positive_replies_a INT DEFAULT 0,
    positive_replies_b INT DEFAULT 0,
    winner TEXT,                  -- 'a', 'b', or NULL if not yet decided
    decided_at TIMESTAMPTZ,      -- When winner was selected (after 200 total sends)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ CONTENT & MARKETING ═══

CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    type TEXT CHECK (type IN ('blog_fr','blog_en','landing_page','social_post','email_template','case_study','faq')),
    title TEXT,
    slug TEXT,
    body TEXT,                -- Markdown or HTML
    keywords TEXT[],
    meta_description TEXT,
    url TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','published','indexed','ranked','killed')),
    metrics JSONB,           -- {impressions, clicks, position, signups}
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE social_posts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    platform TEXT CHECK (platform IN ('reddit','linkedin','twitter','facebook_group')),
    community TEXT,          -- Subreddit name, group name, etc.
    post_type TEXT CHECK (post_type IN ('post','comment','reply')),
    content TEXT,
    url TEXT,
    utm_link TEXT,
    engagement JSONB,        -- {upvotes, comments, shares}
    leads_generated INT DEFAULT 0,
    posted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE referrals (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    referrer_customer_id INT REFERENCES customers(id),
    referee_email TEXT,
    referee_customer_id INT REFERENCES customers(id),
    referral_code TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','signed_up','converted','rewarded')),
    reward_type TEXT,
    reward_applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ OPERATIONS ═══

CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    customer_id INT REFERENCES customers(id),
    job_type TEXT,           -- Business-specific: 'quote','collection','audit','rent_reminder', etc.
    input_data JSONB,
    output_data JSONB,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','escalated')),
    deliverables JSONB,      -- [{type: 'pdf', url: '...'}, ...]
    error TEXT,
    retries INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE support_tickets (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    customer_id INT REFERENCES customers(id),
    channel TEXT CHECK (channel IN ('email','chat','in_app')),
    subject TEXT,
    messages JSONB,          -- [{role: 'customer'|'agent', content, timestamp}]
    status TEXT DEFAULT 'open' CHECK (status IN ('open','pending','resolved','escalated')),
    resolution TEXT,
    response_time_seconds INT,
    csat_score INT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE testimonials (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    customer_id INT REFERENCES customers(id),
    type TEXT CHECK (type IN ('quote','case_study','review','logo_permission')),
    content_fr TEXT,
    content_en TEXT,
    customer_name TEXT,
    customer_company TEXT,
    permission_granted BOOLEAN DEFAULT FALSE,
    published BOOLEAN DEFAULT FALSE,
    published_where TEXT,     -- 'website','capterra','google', etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ KNOWLEDGE BASE (pgvector for RAG) ═══

CREATE TABLE knowledge_base (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    source TEXT CHECK (source IN ('docs','faq','support_ticket','blog','custom')),
    title TEXT,
    content TEXT NOT NULL,
    content_fr TEXT,
    content_en TEXT,
    embedding vector(1536),              -- OpenAI ada-002 or Voyage embeddings
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_kb_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_kb_business ON knowledge_base(business_id, source);

-- ═══ VOICE / TELEPHONY ═══

CREATE TABLE voice_calls (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    lead_id INT REFERENCES leads(id),
    customer_id INT REFERENCES customers(id),
    direction TEXT CHECK (direction IN ('outbound','inbound')),
    call_type TEXT CHECK (call_type IN ('cold_call','qualification','support','payment_followup','appointment_reminder')),
    phone_number TEXT NOT NULL,
    language TEXT DEFAULT 'fr' CHECK (language IN ('fr','en')),
    dncl_checked BOOLEAN DEFAULT FALSE,     -- Was DNCL registry checked before call?
    dncl_clear BOOLEAN,                     -- Was the number NOT on the DNCL?
    retell_call_id TEXT,                    -- Retell/Vapi call ID for traceability
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','ringing','in_progress','completed','failed','no_answer','voicemail','declined')),
    duration_seconds INT,
    transcript TEXT,                        -- Full call transcript
    summary TEXT,                           -- AI-generated call summary
    outcome TEXT CHECK (outcome IN ('interested','not_interested','callback_requested','meeting_booked','wrong_number','voicemail_left','do_not_call','escalate')),
    meeting_booked_url TEXT,                -- Calendly link if meeting booked
    cost_usd NUMERIC(8,4),                 -- Total call cost (Retell + telephony)
    recording_url TEXT,                     -- Call recording URL (if enabled)
    script_variant TEXT,                    -- Which script was used (for A/B testing)
    sentiment_score NUMERIC(3,2),           -- AI-assessed sentiment (-1 to 1)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE dncl_cache (
    id SERIAL PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,      -- E.164 format: +15145551234
    on_dncl BOOLEAN NOT NULL,              -- true = DO NOT CALL
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')  -- DNCL data must be refreshed every 31 days per CRTC rules
);

CREATE TABLE voice_scripts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    call_type TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('fr','en')),
    name TEXT NOT NULL,                     -- e.g., "cold_call_v2_fr"
    system_prompt TEXT NOT NULL,            -- System prompt for the voice AI
    greeting TEXT NOT NULL,                 -- First thing the AI says
    objection_handlers JSONB,              -- {"too_expensive": "response...", "not_interested": "response..."}
    success_criteria TEXT,                  -- What counts as a successful call
    max_duration_seconds INT DEFAULT 120,   -- Hard cutoff
    active BOOLEAN DEFAULT TRUE,
    metrics JSONB,                          -- {calls, connects, conversions, avg_duration}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ SECRETS (API keys, encrypted, managed via Dashboard) ═══

CREATE TABLE secrets (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,          -- e.g. 'ANTHROPIC_API_KEY'
    value_encrypted TEXT NOT NULL,      -- AES-256-GCM encrypted using ENCRYPTION_KEY from .env
    category TEXT NOT NULL CHECK (category IN ('core','lead_gen','infrastructure','outreach','optional')),
    display_name TEXT,                  -- 'Anthropic API Key'
    is_configured BOOLEAN DEFAULT FALSE,
    last_tested_at TIMESTAMPTZ,
    last_test_status TEXT CHECK (last_test_status IN ('ok','failed','untested')),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ INTELLIGENCE ═══

CREATE TABLE agent_logs (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    business_id INT REFERENCES businesses(id),
    workflow_run_id TEXT,     -- Hatchet run ID for traceability
    action TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    result JSONB,
    status TEXT DEFAULT 'success' CHECK (status IN ('success','error','retry','skipped')),
    cost_usd NUMERIC(8,4),   -- API cost of this execution
    duration_seconds NUMERIC(8,2),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE improvements (
    id SERIAL PRIMARY KEY,
    proposed_by TEXT DEFAULT 'self_reflection',
    target_agent TEXT,
    business_id INT REFERENCES businesses(id),
    category TEXT CHECK (category IN ('recurring_error','missed_opportunity','inefficiency','blind_spot','cross_learning','drift','quality','new_idea')),
    description TEXT NOT NULL,
    proposed_action TEXT NOT NULL,
    evidence TEXT,
    impact_score NUMERIC(3,1),
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical','high','medium','low')),
    status TEXT DEFAULT 'proposed' CHECK (status IN ('proposed','approved','implementing','implemented','rejected')),
    outcome TEXT,            -- What happened after implementation
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE daily_snapshots (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    date DATE DEFAULT CURRENT_DATE,
    mrr NUMERIC(10,2),
    customers_active INT,
    customers_new INT,
    customers_churned INT,
    leads_new INT,
    leads_converted INT,
    churn_rate NUMERIC(5,4),
    cac NUMERIC(8,2),
    ltv_estimate NUMERIC(10,2),
    nps_average NUMERIC(4,1),
    api_cost_usd NUMERIC(8,2),
    kill_score NUMERIC(5,2),
    metrics JSONB,           -- Additional business-specific metrics
    UNIQUE(business_id, date)
);

CREATE TABLE budget_tracking (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    agent_name TEXT,
    business_id INT REFERENCES businesses(id),
    api_provider TEXT,       -- 'anthropic','stripe','sendgrid','google_ads','meta_ads', etc.
    cost_usd NUMERIC(8,4),
    tokens_used INT,
    requests_count INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE glossary (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    term_en TEXT NOT NULL,
    term_fr TEXT NOT NULL,
    context TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, term_en)
);

-- ═══ INDEXES ═══
CREATE INDEX idx_ideas_status ON ideas(status);
CREATE INDEX idx_businesses_status ON businesses(status);
CREATE INDEX idx_customers_business ON customers(business_id, status);
CREATE INDEX idx_leads_business ON leads(business_id, status);
CREATE INDEX idx_agent_logs_agent ON agent_logs(agent_name, created_at DESC);
CREATE INDEX idx_agent_logs_business ON agent_logs(business_id, created_at DESC);
CREATE INDEX idx_content_business ON content(business_id, type, status);
CREATE INDEX idx_jobs_business ON jobs(business_id, status);
CREATE INDEX idx_daily_snapshots_lookup ON daily_snapshots(business_id, date DESC);
CREATE INDEX idx_budget_tracking_date ON budget_tracking(date, agent_name);
CREATE INDEX idx_voice_calls_business ON voice_calls(business_id, status, created_at DESC);
CREATE INDEX idx_voice_calls_lead ON voice_calls(lead_id, created_at DESC);
CREATE INDEX idx_dncl_cache_phone ON dncl_cache(phone_number);
CREATE INDEX idx_dncl_cache_expiry ON dncl_cache(expires_at);
```

---

## HATCHET SETUP & AGENT PATTERN

### main.py — Worker Startup

```python
from hatchet_sdk import Hatchet
from src.config import settings
from src.db import engine, SessionLocal

# Import all agents
from src.agents.meta_orchestrator import MetaOrchestrator
from src.agents.idea_factory import IdeaFactory
from src.agents.deep_scout import DeepScout
# ... import all 23+ agents

hatchet = Hatchet()

def main():
    worker = hatchet.worker("factory-worker")
    
    # Register all agent workflows
    worker.register_workflow(MetaOrchestrator)
    worker.register_workflow(IdeaFactory)
    worker.register_workflow(DeepScout)
    # ... register all 23+ agents
    
    worker.start()

if __name__ == "__main__":
    main()
```

### Base Agent Class (every agent inherits this)

```python
# src/agents/base_agent.py
"""
Base class for all agents. Provides:
- Budget circuit breaker (auto-downgrades model tier, hard stops at limit)
- Automatic logging to agent_logs table
- Execution timing
- Error handling with retry context
"""
from src.db import SessionLocal
from src.config import settings
import time

class BaseAgent:
    agent_name: str = "unknown"
    default_model: str = "sonnet"  # Most agents use Sonnet
    
    async def check_budget(self) -> str:
        """Check budget and return the model to use. Auto-downgrades if needed."""
        db = SessionLocal()
        try:
            result = db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) as spent FROM agent_logs WHERE agent_name = :name AND created_at > CURRENT_DATE",
                {"name": self.agent_name}
            ).fetchone()
            daily_spent = float(result.spent)
            
            # Per-agent daily limit (default $5, configurable per agent)
            agent_limit = getattr(settings, f"BUDGET_{self.agent_name.upper()}_DAILY", 5.0)
            
            if daily_spent > agent_limit * 0.8:
                # 80% of budget → downgrade model
                if self.default_model == "opus": return "sonnet"
                if self.default_model == "sonnet": return "haiku"
            
            if daily_spent >= agent_limit:
                raise BudgetExceededError(f"{self.agent_name} daily budget exhausted (${daily_spent:.2f}/${agent_limit:.2f})")
            
            # Also check global daily limit
            global_result = db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) as spent FROM agent_logs WHERE created_at > CURRENT_DATE"
            ).fetchone()
            if float(global_result.spent) >= settings.DAILY_BUDGET_LIMIT_USD:
                raise BudgetExceededError(f"Global daily budget exhausted")
            
            return self.default_model
        finally:
            db.close()
    
    async def log_execution(self, action: str, result: dict, cost: float, duration: float, status: str = "success", error: str = None):
        """Log every execution for Self-Reflection agent to analyze."""
        db = SessionLocal()
        try:
            db.execute(
                """INSERT INTO agent_logs (agent_name, action, result, cost_usd, duration_seconds, status, error_message)
                   VALUES (:name, :action, :result, :cost, :duration, :status, :error)""",
                {"name": self.agent_name, "action": action, "result": json.dumps(result), 
                 "cost": cost, "duration": duration, "status": status, "error": error}
            )
            db.commit()
        finally:
            db.close()

class BudgetExceededError(Exception):
    pass
```

### Agent Pattern (every agent follows this structure)

```python
# src/agents/example_agent.py
from hatchet_sdk import Hatchet, Context
from src.db import SessionLocal
from src.llm import call_claude
from src.config import settings
import json

hatchet = Hatchet()

@hatchet.workflow(
    name="example-agent",
    on_crons=["0 6 * * *"],  # Optional: cron schedule
    timeout="30m",
)
class ExampleAgent:
    
    @hatchet.step(timeout="10m", retries=3)
    async def gather_data(self, context: Context):
        """Step 1: Gather input data from DB and APIs"""
        db = SessionLocal()
        try:
            # Read from shared Postgres state
            data = db.execute("SELECT * FROM businesses WHERE status = 'live'").fetchall()
            return {"businesses": [dict(row) for row in data]}
        finally:
            db.close()
    
    @hatchet.step(timeout="5m", retries=2, parents=["gather_data"])
    async def analyze(self, context: Context):
        """Step 2: Use Claude to analyze the data"""
        prev = context.step_output("gather_data")
        
        system_prompt = open("prompts/example_agent.txt").read()
        
        result = await call_claude(
            model="claude-sonnet-4-20250514",  # or opus for complex reasoning
            system=system_prompt,
            user=json.dumps(prev),
            max_tokens=4096,
        )
        return {"analysis": result}
    
    @hatchet.step(timeout="5m", retries=3, parents=["analyze"])
    async def execute(self, context: Context):
        """Step 3: Take action based on analysis"""
        analysis = context.step_output("analyze")
        
        db = SessionLocal()
        try:
            # Write results to shared state
            db.execute(
                "INSERT INTO agent_logs (agent_name, action, result) VALUES (%s, %s, %s)",
                ("example_agent", "daily_run", json.dumps(analysis))
            )
            db.commit()
        finally:
            db.close()
        
        # Optionally trigger another agent
        hatchet.client.admin.run_workflow(
            "next-agent",
            input={"trigger": "from_example_agent", "data": analysis}
        )
        
        return {"status": "completed"}
```

---

## ALL 23 AGENTS — SPECIFICATIONS

Each agent below needs its own Python file following the pattern above. I'm specifying: trigger, steps (as Hatchet DAG), inputs, outputs, Claude model to use, and the system prompt file content.

### Agent 1: META ORCHESTRATOR (`meta_orchestrator.py`)

**Trigger:** Cron daily 6:00 AM ET (daily review) + **EVENT-DRIVEN** (triggered immediately when any pipeline event occurs)

**CRITICAL CHANGE: The Meta Orchestrator is NOT a bottleneck.** It does daily reviews, but the pipeline advances in REAL-TIME via event cascading. When Idea Factory scores an idea ≥ 7, Scout triggers IMMEDIATELY — it doesn't wait for Meta's next morning cron.

**Event cascade (runs within minutes, not days):**
- Idea scored ≥ 7.0 → IMMEDIATELY trigger Deep Scout (parallel: multiple ideas can be scouted simultaneously)
- Scout says GO → IMMEDIATELY trigger Validator (Brand light mode runs first, then landing page + ads)
- Validator says GO (after 7 days of ads) → IMMEDIATELY trigger Brand full mode → Domain Provisioner → Builder (these 3 run in sequence but START within minutes of validation completing)
- Builder deploys → IMMEDIATELY trigger Distribution Engine (Lead Pipeline starts finding leads)
- Lead Pipeline finds leads → IMMEDIATELY trigger Enrichment → Outreach begins

**Parallelism:** The factory can run MULTIPLE pipelines simultaneously:
- Idea A in validation + Idea B in scouting + Business C live and selling — all at the same time
- Hatchet handles concurrency natively. Each business gets its own workflow runs.
- Budget Guardian enforces total daily spend cap across all parallel workflows.

**The daily 6AM cron is for OVERSIGHT only:**
- Review metrics across all businesses
- Reallocate budgets
- Flag problems
- Generate Slack digest
- Kill/escalate decisions
- It does NOT advance the pipeline — events do that
**Claude model:** claude-opus-4-20250514 (needs deep reasoning)
**Steps DAG:**
1. `gather_all_metrics` — Read from: daily_snapshots, agent_logs (last 24h errors), improvements (pending), businesses (status), budget_tracking (yesterday)
2. `analyze_and_decide` — Send all data to Claude Opus with system prompt. Get back: priorities, agent triggers, budget allocation, human alerts.
3. `execute_decisions` — Write decisions to agent_logs. Trigger relevant agents via `hatchet.client.admin.run_workflow()`. Send Slack digest.

**System prompt:** (save as `prompts/meta_orchestrator.txt`)
```
Tu es le CEO Agent de la Factory. Tu coordonnes 23 agents autonomes qui opèrent des micro-business SaaS au Canada.

CHAQUE MATIN tu reçois:
- MRR par business, tendance 7j et 30j
- Nombre de clients actifs, nouveaux, churnés (par business)
- Logs d'erreur des agents (dernières 24h)
- Propositions d'amélioration du Self-Reflection Agent
- Budget API dépensé hier vs budget alloué
- Pipeline leads par business

TON JOB — produis un JSON avec exactement ces clés:
{
  "priorities": ["top 3 priorities for today"],
  "agent_triggers": [
    {"agent": "workflow-name", "input": {}, "reason": "why"}
  ],
  "budget_allocation": {"business_slug": dollars_per_day},
  "alerts": ["anything the human needs to see"],
  "human_needed": ["decisions only a human can make"],
  "reasoning": "brief explanation of your logic"
}

RÈGLES:
- Budget API total: max $50/jour. JAMAIS dépasser.
- Business en validation: max 14 jours, $300 total. Après → kill ou go.
- MRR stagne 30 jours → recommande pivot/double-down/kill
- Agent error rate >20% → alerte immédiate
- Priorise: clients existants > acquisition > nouveau business
- Chaque business DOIT être bilingue FR/EN et clairement canadien
```

---

### Agent 2: IDEA FACTORY (`idea_factory.py`)

**Trigger:** Cron DAILY 5:00 AM (not weekly) + On-demand via Meta or Dashboard
**Claude model:** claude-sonnet-4-20250514
**Steps DAG:**
1. `scrape_sources` — HTTP requests to: Google Trends (compare US vs CA), Product Hunt API, Y Combinator directory, IndieHackers, Reddit (r/SaaS, r/smallbusiness, r/entrepreneur), Shopify App Store, AppSumo. Parse results.
2. `filter_canadian_gap` — For each idea found, search Google.ca and Capterra (filter CA) to check if a Canadian equivalent exists. Keep only ideas where gap exists.
3. `score_ideas` — Send each idea to Claude Sonnet for scoring on 12 criteria (see prompt). Score ≥ 7.0 → mark as 'scouting' in DB.
4. `save_and_cascade` — Write scored ideas to `ideas` table. **For EACH idea scoring ≥ 7.0, IMMEDIATELY trigger Deep Scout** via `hatchet.client.admin.run_workflow("deep-scout", {"idea_id": id})`. Multiple scouts can run in parallel. Notify Slack.

**Parallelism:** If Idea Factory finds 3 ideas scoring ≥ 7.0 in one run, it triggers 3 Deep Scout runs simultaneously. No queue, no waiting.

**System prompt:** (save as `prompts/idea_factory.txt`)
```
Tu es l'Idea Factory. Ton job: trouver des business SaaS qui marchent aux USA mais qui N'EXISTENT PAS au Canada.

Tu reçois des données brutes scrapées de: Google Trends, Product Hunt, Y Combinator, Reddit, Shopify App Store, AppSumo.

Pour chaque idée potentielle, score-la sur ces 12 critères (/10 chacun):
1. Douleur client (récurrence, intensité)
2. Willingness to pay (le client paie-t-il déjà aux US?)
3. Defensibilité vs ChatGPT (reste-t-il un produit utile sans l'IA?)
4. Taille du marché CA (minimum 5000 entreprises cibles)
5. Compétition locale au Canada (moins = mieux)
6. ARPU potentiel (>$100/mo = bien)
7. Complexité technique du MVP (moins = mieux)
8. Time to first revenue (<60 jours = bien)
9. Potentiel de récurrence (MRR vs one-time)
10. Avantage bilingue/canadien spécifique
11. Potentiel d'expansion internationale
12. Compatibilité avec notre stack (Next.js, Supabase, Stripe)

Réponds UNIQUEMENT en JSON array:
[{
  "name": "string",
  "niche": "string",
  "us_equivalent": "company name",
  "us_equivalent_url": "https://...",
  "ca_gap_analysis": "why this doesn't exist in Canada",
  "score": 8.5,
  "scoring_details": {"criterion_1": 9, ...},
  "tam_estimate": "~X businesses in Canada",
  "pricing_hypothesis": "$X/mo based on Y",
  "mvp_complexity": "low|medium|high"
}]
```

---

### Agent 3: DEEP SCOUT (`deep_scout.py`)

**Trigger:** On-demand (triggered by Meta when idea score ≥ 7)
**Claude model:** claude-opus-4-20250514 (needs deep research synthesis)
**Steps DAG:**
1. `research_market` — Scrape: Statistique Canada (NAICS codes), provincial business registries, Google.ca for competitors, industry associations.
2. `analyze_us_competitor` — Scrape the US equivalent's website thoroughly: pricing page, features page, about page, blog, testimonials. Screenshot or save key pages for Brand Agent.
3. `discover_channels` — Query SparkToro API with ICP description (e.g., "small roofing contractors in Quebec") to get audience intelligence: websites visited, social accounts followed, podcasts, subreddits, Facebook groups. Score each channel using ICE (Impact × Confidence × Ease, 1-10 each). Also: search for industry associations using Associations Canada database + Google ("[industry] association Quebec/Canada"), identify relevant app marketplaces/ecosystems (QuickBooks, Shopify, Jobber, etc.), and find community gathering spots (Facebook Groups, forums, trade shows).
4. `research_regulations` — Search for provincial regulations, bilingual requirements, industry certifications, CASL requirements.
5. `generate_gtm_playbook` — Using all research, generate the GTM Playbook YAML config (see §13 above). This is the MOST IMPORTANT output — it configures ALL downstream sales/growth agents for this business. Include: ICP params, ranked channels, lead sources, association list, ecosystem integrations, messaging frameworks, signal definitions, outreach cadence, and referral program design.
6. `synthesize_report` — Send all research to Claude Opus. Generate comprehensive Scout Report (markdown). Include US competitor branding analysis.
7. `save_and_cascade` — Save Scout Report to `ideas.scout_report`. Save GTM Playbook to `gtm_playbooks` table. Update status. **If GO → IMMEDIATELY trigger Validator** via `hatchet.client.admin.run_workflow("validator", {"idea_id": id})`. If NO-GO → mark idea as 'killed' and notify Slack. No waiting for Meta Orchestrator.

**System prompt:** (save as `prompts/deep_scout.txt`)
```
Tu es le Deep Scout. Tu fais un deep dive complet sur une idée de business SaaS pour le marché canadien.

Tu reçois: l'idée avec son score initial + des données brutes de recherche.

Produis un SCOUT REPORT en Markdown avec ces sections exactes:

# Scout Report: [Nom de l'idée]

## Executive Summary
3 phrases: opportunité, taille, recommandation.

## Market Size & Dynamics
- TAM canadien (nombre d'entreprises, revenus potentiels)
- Croissance du marché
- Saisonnalité

## Competitive Landscape
- Concurrents canadiens (avec URLs et pricing)
- Concurrents US (détaillé)
- Gaps dans l'offre existante

## US Competitor Branding Analysis
CRITIQUE — le Brand Agent utilisera cette section:
- URL du site
- Palette de couleurs utilisée
- Typographie
- Ton de voix (formal/casual, tu/vous)
- Hero section messaging
- Points forts du design
- Points faibles du design
- Screenshots/descriptions des pages clés

## ICP (Ideal Customer Profile)
- NAICS code(s)
- Taille d'entreprise
- Rôle du décideur
- Budget typique
- Pain points quotidiens (verbatim si possible)
- Signaux d'achat (quels événements indiquent qu'ils ont besoin du produit MAINTENANT?)
- Stack technique actuel (quel logiciel utilisent-ils? Excel? Papier? Un concurrent?)
- Où ils traînent en ligne (SparkToro data si disponible)
- Comment ils préfèrent être contactés (email? téléphone? SMS? Facebook?)

## Channel Strategy (ICE scored)
Pour chaque channel, score Impact × Confidence × Ease (1-10 chaque):
- Top 3 channels d'acquisition recommandés avec scores ICE
- Associations professionnelles pertinentes (nationales ET provinciales) avec URLs
- App marketplaces/écosystèmes pertinents (QuickBooks, Shopify, etc.)
- Subreddits spécifiques avec nombre de membres
- Facebook Groups spécifiques avec nombre de membres
- Événements/salons professionnels à venir
- Mots-clés SEO FR et EN (programmatic templates inclus)
- Partenaires potentiels (fournisseurs, comptables, consultants qui servent le même ICP)

## Signaux d'achat à surveiller
Liste des événements qui indiquent un prospect chaud:
- Nouvelles inscriptions au REQ
- Permis de construction émis
- Embauches dans le rôle que le produit remplace
- Plaintes sur Google Reviews/Facebook contre des concurrents
- Changements réglementaires affectant l'industrie

## Recommended Pricing
- Prix suggéré en CAD
- Comparaison avec le concurrent US
- Justification

## Regulations & Compliance
- Exigences provinciales
- Bilinguisme (Loi 101)
- Certifications requises

## Risks & Mitigations

## GO / NO-GO Recommendation
Avec score de confiance (1-10) et justification.

Aussi, produis un JSON résumé pour le GTM Playbook (ce JSON sera converti en config YAML et stocké dans gtm_playbooks):
{
  "go_nogo": "go|nogo",
  "confidence": 8,
  "icp": {
    "naics_codes": ["238160"],
    "company_size": "1-25",
    "decision_maker_titles": ["owner", "président"],
    "geo": "QC",
    "language": "fr",
    "tech_signals": ["no_website", "spreadsheet_user"],
    "pain_keywords": ["estimation longue", "soumission perdue"]
  },
  "us_competitor_analysis": {...},
  "channels_ranked": [
    {"channel": "cold_email", "impact": 8, "confidence": 7, "ease": 6, "ice": 336},
    {"channel": "association_partnership", "impact": 9, "confidence": 6, "ease": 5, "ice": 270},
    {"channel": "facebook_groups", "impact": 7, "confidence": 8, "ease": 6, "ice": 336}
  ],
  "lead_sources": [
    {"type": "google_maps", "query": "couvreur toiture", "geo": "QC"},
    {"type": "rbq_registry", "licence_type": "couvreur"},
    {"type": "association_directory", "org": "AMCQ", "url": "amcq.qc.ca/membres/"}
  ],
  "associations": [
    {"name": "AMCQ", "url": "amcq.qc.ca", "type": "direct_niche"},
    {"name": "APCHQ", "url": "apchq.com", "type": "umbrella"}
  ],
  "ecosystems": [
    {"platform": "QuickBooks", "integration_type": "export"}
  ],
  "signals": [
    {"type": "new_business_registration", "source": "req_registry", "weight": 9},
    {"type": "building_permit_issued", "source": "municipal_data", "weight": 8}
  ],
  "messaging": {
    "value_prop_fr": "...",
    "value_prop_en": "...",
    "pain_points": [...],
    "tone": "direct, tutoiement",
    "frameworks": ["pain_agitate_solve"]
  },
  "pricing_recommendation": {...},
  "top_keywords_fr": [...],
  "top_keywords_en": [...],
  "referral": {"incentive": "1_month_free", "type": "double_sided"}
}
```

---

### Agent 4: VALIDATOR (`validator.py`)

**Trigger:** On-demand (triggered IMMEDIATELY by Deep Scout on GO — not waiting for Meta)
**Claude model:** claude-sonnet-4-20250514
**Steps DAG:**
1. `request_light_brand` — Trigger Brand Agent in light mode. Wait for response (brand_kit_light with colors, font, tone).
2. `generate_landing_page` — Use Claude to generate bilingual HTML landing page using brand kit + Scout Report ICP data. Must include: FR/EN toggle, email capture form, headline addressing pain point, social proof placeholder, favicon, meta tags, privacy link.
3. `deploy_landing` — Push HTML to Vercel via API (or use a temporary Supabase project for the form backend). Set up email capture endpoint.
4. `launch_ads` — Create Google Ads campaign (2-3 keywords, $75 budget) + Meta Ads campaign (ICP targeting, $75 budget) via APIs.
5. `monitor_daily` — Sub-cron: check ad metrics daily for 7 days. Log to DB.
6. `evaluate_results` — After 7 days: compile metrics (CPC, CTR, signup rate, cost per lead, FR vs EN split). Use Claude to analyze. Produce GO/KILL recommendation.
7. `cascade_on_result` — Save results. **If GO or STRONG GO (signup ≥ 3%) → IMMEDIATELY trigger the build pipeline** in sequence: Brand full mode → Domain Provisioner → Builder. These 3 cascade automatically. **If weak signal (signup 1-3%) → notify Dashboard for human GO/KILL decision.** If KILL (signup < 1%) → mark idea as killed, tear down landing page, notify Slack.

**Kill rules (hardcoded, not LLM-decided):**
- CPC > $8 after 3 days → pause ads, recommend messaging pivot
- Signup rate < 1% after 7 days → auto-kill (no interest at all)
- Signup rate 1-3% → decent for cold traffic to unknown brand, notify Dashboard for human GO/KILL
- Signup rate 3-5% → GO (above SaaS median of 3.8% from cold paid traffic)
- Signup rate > 5% → STRONG GO, auto-cascade to build pipeline immediately

**Why these numbers:** The median SaaS landing page converts at 3.8% — but that's for ESTABLISHED brands with recognition. A brand-new, unknown, AI-generated landing page receiving cold paid traffic from Google/Meta ads should expect lower. Getting 1-3% from cold traffic to an unknown brand is actually a positive signal. Getting > 3% means real demand. Getting > 5% is exceptional and means you should build immediately.

---

### Agent 5: BRAND DESIGNER (`brand_designer.py`)

**Trigger:** On-demand (two modes: 'light' for pre-validation, 'full' for pre-build)
**Claude model:** claude-opus-4-20250514 (creative + analytical)
**Steps DAG:**

LIGHT MODE:
1. `quick_brand` — Use US competitor analysis from Scout Report. Generate: 2 primary colors, 1 accent, heading font, body font, FR/EN tone examples, 2 name options, check domain availability via Namecheap API.

FULL MODE:
1. `research_inspiration` — Scrape competitor US site + 3-5 SaaS sites in adjacent niches (from Dribbble, Land-book, Awwwards via search).
2. `generate_brand_kit` — Claude Opus generates full brand kit.
3. `check_domains` — Namecheap API: check .ca and .com for all name options.
4. `save_brand_kit` — Save to `businesses.brand_kit` as JSONB.
5. `cascade_to_provisioner` — **IMMEDIATELY trigger Domain Provisioner** via `hatchet.client.admin.run_workflow("domain-provisioner", {"business_id": id})`

**System prompt:** (save as `prompts/brand_designer.txt`)
```
Tu es le Brand & Design Agent. Tu crées l'identité visuelle de chaque business.

Tu reçois: Scout Report avec analyse du branding du concurrent US.

PRODUIS UN BRAND KIT — JSON exact:
{
  "name_options": [
    {"name": "string", "domain_ca": "available|taken", "domain_com": "available|taken", "rationale": "why this name"}
  ],
  "recommended_name": "string",
  "colors": {
    "primary": "#hex",
    "secondary": "#hex",
    "accent": "#hex",
    "background_light": "#hex",
    "background_dark": "#hex",
    "text_primary": "#hex",
    "text_secondary": "#hex",
    "success": "#hex",
    "warning": "#hex",
    "error": "#hex"
  },
  "typography": {
    "heading": "Font Name (from Google Fonts)",
    "body": "Font Name (from Google Fonts)",
    "mono": "Font Name (for code/data)"
  },
  "tone": {
    "fr": {
      "formality": "tu|vous",
      "headline_example": "string",
      "cta_example": "string",
      "error_message_example": "string"
    },
    "en": {
      "headline_example": "string",
      "cta_example": "string",
      "error_message_example": "string"
    }
  },
  "mood_board_urls": ["5-10 URLs of design inspiration"],
  "canadian_identity": {
    "tagline_fr": "Conçu au Québec" or similar,
    "tagline_en": "Made in Canada" or similar,
    "subtle_elements": "description of how to integrate Canadian identity without being heavy-handed"
  },
  "competitor_inspiration": {
    "borrow": ["what to take from the US competitor design"],
    "avoid": ["what to NOT copy"]
  },
  "logo_concept": "Description of a simple text-based logo using the heading font. NO generated images. Just styled text."
}

RÈGLES:
- Le nom doit fonctionner en FR ET EN (pas de jeu de mots unilingue)
- Court: max 3 syllabes
- PAS de suffixes -ly, -fy, -AI, -Bot, -Hub
- PAS de gradients purple-on-white (cliché IA 2025)
- PAS de Inter, Roboto, Arial
- Le site doit paraître fait par une agence de design, PAS par un vibe coder
- Couleurs: inspirées du concurrent US mais différenciées
- Suggérer des fonts de: Satoshi, General Sans, Switzer, Cabinet Grotesk, Plus Jakarta Sans, Outfit, Sora, Manrope
```

---

### Agents 6-27: SPECIFICATION SUMMARY

For the remaining agents, here are the key specifications. Each follows the same Hatchet pattern.

#### Agent 6: DOMAIN PROVISIONER (`domain_provisioner.py`)
- **Trigger:** On-demand — cascaded from Brand Designer (full mode complete) or manually from Dashboard
- **Steps:** buy_primary_domain (Namecheap: .ca preferred, set NS to Cloudflare) → buy_secondary_cold_email_domains (Namecheap: buy 2-3 alternate TLDs like .io, .co for cold outreach — NEVER send cold email from the primary .ca domain) → setup_dns_all_domains (Cloudflare: A, MX, TXT for SPF/DKIM/DMARC on ALL domains) → create_vercel_project → create_github_repo (clone template) → create_supabase_project (enable RLS on every table) → setup_stripe (reverse trial product + free tier + paid tiers in CAD) → setup_resend (transactional on primary domain) → setup_instantly (cold email on secondary domains, start warmup) → buy_twilio_number (local area code: 514 QC, 416 ON, etc.) → create_retell_agents (FR + EN per business) → save_infra_to_db → **IMMEDIATELY trigger Builder** via `hatchet.client.admin.run_workflow("builder", {"business_id": id})`
- **Critical:** Stripe SINGLE account mode. Secondary domains for cold email (toituro.io for cold, toituro.ca for transactional). Warmup 4-6 weeks on cold domains before volume.
- **Stripe setup:** Create 3 products per business: Free tier, Pro tier ($X/mo), Business tier ($Y/mo). Create a trial configuration for reverse trial (14 days, auto-downgrade to Free). Annual variants at 16-20% discount.

#### Agent 7: BUILDER (`builder.py`)
- **Trigger:** On-demand from Domain Provisioner (infra ready)
- **Steps:** generate_architecture (Claude Opus) → generate_code (Claude Sonnet, iterative) → push_to_github → deploy_vercel → run_lighthouse → generate_docs → create_marketplace_integration → **cascade_to_distribution** (IMMEDIATELY trigger Distribution Engine Lead Pipeline for this business) → notify_slack ("🚀 [Business Name] is LIVE at [domain]. Distribution Engine starting.")
- **Critical:** Uses the template repo (Next.js + next-intl + Tailwind + Supabase Auth + Stripe + blog + referral system). Brand Kit applied. Bilingual from day 1.
- **ONBOARDING (see §5 above):** NEVER show empty dashboard after signup. Pre-populate a sample project with AI. Max 3 signup fields. Aha moment in <2 minutes. Onboarding checklist with progress bar. SMS notifications for trades users.
- **REVERSE TRIAL (see §4 above):** All new users get 14-day full premium access. Auto-downgrade to free tier after 14 days (Stripe handles via scheduled subscription change). Upgrade CTA shows what they're losing.
- **PRICING (see §8 above):** Flat-rate CAD pricing. Charm pricing ($49 not $50). 3 tiers with middle as recommended. Annual billing 16-20% discount.
- **RLS (see §12 above — NON-NEGOTIABLE):** Every `CREATE TABLE` in every migration MUST include `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` with proper policies scoped by business_id. The Builder agent must verify this after every code generation.
- **ECOSYSTEM INTEGRATION:** For each business, build a basic integration with the #1 tool the ICP already uses (e.g., QuickBooks export for Quote OS, Shopify app for Compliance Ops) and submit to their marketplace. Free acquisition channel.
- **DATA FLYWHEEL (see §10 above):** Design schemas so every user action (quote generated, payment collected, audit completed) contributes to aggregate data that improves the product for all users. This is your moat.
- **Template repo must include:** i18n (next-intl), language toggle, blog with MDX, referral system, reverse trial logic, legal page templates, onboarding checklist component, support widget, `/llms.txt` auto-generation, `/llms-full.txt` generation, `.md` page routes, schema.org components, AI-friendly `robots.txt`, Plausible Analytics script, SMS notification integration (Twilio).

#### Agent 8: i18n AGENT (`i18n_agent.py`)
- **Trigger:** After every deploy + weekly scan
- **Steps:** pull_messages_files → validate_completeness (all keys in fr.json exist in en.json and vice versa) → quality_check_fr (Claude: natural québécois?) → quality_check_en (Claude: natural Canadian English?) → update_glossary → report_issues
- **Maintains:** `glossary` table per business

#### Agent 9: CONTENT ENGINE (`content_engine.py`)
- **Trigger:** Cron Mon+Thu 7AM + after new business launch + after every deploy (regenerate llms-full.txt)
- **Reads:** `gtm_playbooks.messaging.top_keywords_fr/en` + `gtm_playbooks.icp` for targeting
- **Two modes:**
  - **EDITORIAL MODE:** keyword_research (DataForSEO API or Ahrefs API + People Also Ask + LLM-style questions) → competitor_content_analysis → write_article_fr (Claude Sonnet) → write_article_en (Claude Sonnet, different keywords not translation) → push_to_github → submit_to_google_indexing_api → update_sitemap → regenerate_llms_full_txt → log_content
  - **PROGRAMMATIC SEO MODE (highest leverage for scaling):** Generate templated pages at scale from database. Universal templates that work across all verticals:
    - `[Product] for [sub-vertical]` → "Quote OS pour couvreurs", "Quote OS pour plombiers", "Quote OS pour électriciens"
    - `[Product] vs [Competitor]` → comparison pages for every discovered competitor
    - `Best [category] software in [province]` → "Meilleur logiciel de soumission au Québec"
    - `[Product] + [Integration]` → "Quote OS + QuickBooks", "Quote OS + Acomba"
    - `How to [workflow] in [province]` → "Comment faire une soumission de toiture au Québec"
    - `[Industry] [metric] Canada [year]` → "Coûts moyens de toiture par ville au Québec — 2026" (data-as-marketing)
    - Template: generate once, populate from database per business, publish automatically. Zapier-style scale (5,000+ pages possible).
- **Volume:** 3-5 editorial articles/week + 20-50 programmatic pages at launch per business, in BOTH languages
- **GEO responsibilities (in addition to SEO):**
  - Every article includes a "Quick Answer" section at the top (2-3 sentences that an LLM would directly quote)
  - Include specific data points and numbers (LLMs cite specifics, not vague statements)
  - Target question-format keywords: "How do I estimate a roofing job in Quebec?" not just "roofing estimation software"
  - After each publish: regenerate `/llms-full.txt` on the business site (flattened Markdown of all pages)
  - Monthly: create/update a "Best [category] in Canada" comparison page per business (LLMs love citing these)
  - Monthly: refresh key pages (pricing, features) with "Last updated: [date]" timestamp (freshness signal)
  - Ensure business name + niche + "Canada" co-occur naturally across multiple pages (entity positioning)

#### Agent 10: SOCIAL AGENT (`social_agent.py`)
- **Trigger:** Cron 3x/day + event-driven (new content published) + signal-triggered (community mention detected)
- **Reads:** `gtm_playbooks.channels` for which communities to monitor
- **Steps:** monitor_communities (Syften.com $19-79/mo for keyword alerts across Reddit, FB, forums) → identify_opportunities (pain point discussions, recommendation requests, competitor complaints) → generate_response (Claude Haiku, contextual, value-first, 90% helpful / 10% subtle mention) → post_or_comment (Reddit API / Facebook API) → track_utm → log_engagement
- **ANTI-BAN RULES (critical — 80% of SaaS companies get banned from Reddit in first month):**
  - Use a real persona account, not a brand account
  - 90/10 rule: 90% genuinely helpful comments with NO product mention, 10% contextual mentions
  - Never post the same link twice. Vary domains. No self-promotional post titles.
  - Reddit: comment karma must be > 100 before any product mention. Build karma first with genuine contributions.
  - Facebook Groups: read rules before posting. Many groups ban links entirely. Provide value in text, offer to DM link if interested.
  - Track per-community: if any post gets removed or reported, pause that community for 14 days.
- **LinkedIn:** Founder-persona posts 3x/week (thought leadership, not product promotion). FR content for QC audience, EN for ROC. This is the top organic B2B social channel.
- **Monitoring → Signal pipeline:** When a community mention matches a lead in our `leads` table → flag as warm signal → push to Signal Monitor → priority outreach.

#### Agent 11: REFERRAL AGENT (`referral_agent.py`)
- **Trigger:** Event-driven (NPS response submitted, referral code used, new signup)
- **Reads:** `gtm_playbooks.referral` for incentive config
- **Steps:** 
  - `nps_trigger` → When NPS score ≥ 9 submitted, IMMEDIATELY present personalized referral invitation with pre-filled sharing templates (email, SMS, WhatsApp). This is the highest-conversion moment.
  - `generate_referral_assets` → Per-user referral link + shareable quote image + pre-written message in user's language
  - `track_referral_usage` → Attribute signups to referrer via code
  - `apply_reward` → Double-sided: both referrer AND referee get reward (1 month free, credit, or upgrade — configurable per playbook). Stripe credit API.
  - `identify_power_referrers` → Users with ≥3 successful referrals → upgrade to "ambassador" tier (permanent discount + early access + featured testimonial)
  - `nudge_non_sharers` → 5-7 days after NPS ≥ 8 with no share → gentle SMS reminder ("Tu as aimé [product]? Ton code donne 1 mois gratuit à tes collègues: [link]")
  - `track_channel_performance` → SMS referral requests generate 4x higher response than email. Prioritize SMS for trades ICPs, email for professional services.
- **84% of B2B buyers enter the sales cycle through a referral. This agent is critical from Month 1.**

#### Agent 12: DISTRIBUTION ENGINE (`distribution/` — 5 sub-agents)

**This is the most important agent in the factory. It reads from the GTM Playbook config (§13) and autonomously sells ANY business.**

The Distribution Engine is 5 sub-agents that share the GTM Playbook config for each business. Changing verticals means changing the playbook YAML, not the code.

**Sub-agent 12a: LEAD PIPELINE (`distribution/lead_pipeline.py`)**
- **Trigger:** Cron daily 6AM per active business
- **Reads:** `gtm_playbooks.lead_sources` for this business
- **Steps:** For each configured lead source in priority order:
  - `google_maps` → Serper Maps API ($0.20/1000 leads). ZIP-code sector strategy for comprehensive coverage. Extract: name, phone, website, address, rating, review count.
  - `rbq_registry` → Download RBQ open data CSV (50K+ contractor licences, free). Filter by licence type matching NAICS. New leads only (compare against existing `leads` table).
  - `req_registry` → Query REQ for new business registrations matching NAICS codes. Batch extract ($134/compilation) or per-lookup API. Focus on registrations from last 30 days (signal: new businesses need software).
  - `federal_corp_api` → Canada API Store, free. Search by industry keywords.
  - `association_directory` → Scrape member directories of configured associations (AMCQ, APCHQ, etc.). Respect rate limits.
  - `industry_directory` → Scrape configured directories (BâtiGuide 44K+ entries, JeBatimatech, Portail Constructo, etc.)
- **Dedup:** Fuzzy match on business name + address (Canada Post API for address standardization). Merge, don't duplicate.
- **Output:** New leads inserted into `leads` table with `source`, `source_url`, and `business_id`.

**Sub-agent 12b: ENRICHMENT AGENT (`distribution/enrichment.py`)**
- **Trigger:** After Lead Pipeline completes, or on-demand for new leads
- **Waterfall enrichment (run in order, stop when found):**
  1. Apollo.io API → email + phone + title + company size (275M+ contacts, free tier)
  2. Hunter.io API → domain-based email finding ($49/mo for 500 lookups)
  3. Dropcontact API → GDPR-compliant email enrichment (EU-focused but works for CA)
  4. Website scrape → find /contact, /about, /team pages, extract emails + phones with regex + Claude
  5. LinkedIn profile match → match by name + company (manual research agent, rate-limited)
- **Verification:** ZeroBounce API on every email before it enters outreach queue. Remove catch-alls and invalids.
- **Lead scoring:** Score 0-100 based on:
  - ICP match (NAICS, size, geo, language) — 40 points max
  - Signal recency (has a buying signal in last 30 days?) — 30 points max
  - Contact quality (verified email + phone vs just email) — 15 points max
  - Tech stack match (no website = likely manual process = high intent) — 15 points max
- **Output:** Enriched leads with `email`, `phone`, `score`, `enrichment_sources`, `consent_type` (for CASL: "conspicuous_publication" or "business_relationship" etc.)

**Sub-agent 12c: SIGNAL MONITOR (`distribution/signal_monitor.py`)**
- **Trigger:** Cron every 4 hours + webhook listeners
- **Reads:** `gtm_playbooks.signals` for each business
- **Monitors (configurable per playbook):**
  - `new_business_registration` → Poll REQ API for new registrations in target NAICS codes. Alert within 24h.
  - `building_permit_issued` → Scrape municipal open data portals (Montreal, Quebec City, etc.) for new permits.
  - `competitor_complaint` → Monitor Google Reviews + Facebook mentions of known competitors. Claude classifies sentiment.
  - `job_posting` → Scrape Indeed.ca / LinkedIn Jobs for roles the product replaces (e.g., "estimateur" for Quote OS).
  - `website_visitor` → Plausible API webhook when company matches lead in `leads` table (IP → company matching via Clearbit Reveal or similar).
  - `regulation_change` → Monitor Gazette officielle du Québec, CRTC, CRA for regulatory changes relevant to ICP.
  - `association_event` → Scrape configured association event pages for upcoming events.
- **On signal detected:** Update `leads.signal_type`, `leads.signal_date`, `leads.signal_data`. Bump lead score by signal weight. If lead is already in outreach sequence → move to priority queue. If new lead → fast-track into enrichment + outreach.
- **Signal-specific email templates:** Each signal type maps to a personalization template in the playbook config. "new_business" → congratulatory angle. "competitor_complaint" → empathy + alternative angle. "job_posting" → automation angle.

**Sub-agent 12d: OUTREACH AGENT (`distribution/outreach.py`)**
- **Trigger:** Daily after enrichment completes + on-demand for signal-triggered leads
- **Reads:** `gtm_playbooks.messaging` + `gtm_playbooks.outreach` for templates and cadence
- **TIERED AUTONOMY (see §13.C):**
  - Week 1-2: ALL messages posted to Slack #outreach-review channel. Human approves or edits before sending.
  - Week 3-4: Auto-send for leads scoring < 70. Human reviews leads scoring ≥ 70 (high-value).
  - Month 2+: Full autonomy for validated playbook configs. Human reviews only when reply rate drops below 2%.
- **Message generation:** Claude Haiku generates personalized message using:
  - Playbook messaging config (value prop, pain points, tone, frameworks)
  - Lead data (name, company, role, industry-specific details from enrichment)
  - Signal data if available (specific trigger referenced in opening)
  - CASL compliance metadata (consent type, unsub link, physical address, sender ID)
- **Multi-channel sequence (configurable per playbook):**
  - Default cadence: Email 1 (Day 0) → Email 2 (Day 3) → Email 3 + Loom link (Day 7) → Breakup email (Day 12)
  - If lead has LinkedIn profile → add LinkedIn connection request between Email 1 and 2
  - If lead replied positively → trigger Voice Agent for warm call (see §2)
  - Max 50 emails/day/domain during first month, scale to 200 after warmup
- **A/B testing:** For each business, run 2 subject line variants and 2 opening line variants. After 200 sends, auto-select winner. Log all variants and results to `outreach_experiments` table.
- **CRITICAL 2026 rules:** Secondary domains only. Under 80 words. No links email 1. SPF/DKIM/DMARC. Track replies not opens. Log email source for CASL.

**Sub-agent 12e: REPLY HANDLER (`distribution/reply_handler.py`)**
- **Trigger:** Webhook from Instantly.ai on new reply + Cron every 30min to check
- **Classification (Claude Haiku):** Categorize each reply as:
  - `positive_interested` → Route to Voice Agent for warm call. Or if no phone, send demo link + reverse trial signup.
  - `positive_question` → Generate answer using product knowledge base (RAG) + send reply. Keep in sequence.
  - `negative_not_interested` → Mark lead as closed-lost. Add to suppression list. Send polite acknowledgment.
  - `negative_competitor` → Log competitor name. Mark closed-lost. Feed data to Competitor Watch agent.
  - `objection` → Claude generates objection handling using playbook messaging. Route to human if high-value account.
  - `ooo_autoresponder` → Snooze sequence, retry after return date.
  - `unsubscribe` → Immediately suppress. CASL compliance: process within 10 business days (we do it instantly).
  - `wrong_person` → Ask for referral to right person. Update lead record.
- **Escalation:** Any reply that Claude classifies with < 80% confidence → route to Slack for human review.
- **Metrics:** Track positive reply rate, meeting book rate, demo-to-trial rate, trial-to-paid rate per business per channel per message variant.

#### Agent 13: EMAIL NURTURE (`email_nurture.py`)
- **Trigger:** Event-driven (signup, inactivity detected, churn) + cron for newsletters
- **Sequences:** Onboarding (6 emails/30 days), Newsletter (bi-weekly), Re-engagement (14+ days inactive), Post-churn (30/90 day win-back)
- **Critical:** Frequency cap: max 3 emails/week per user across ALL agents. Bilingual (user's language preference). CASL unsub.

#### Agent 14: SOCIAL PROOF COLLECTOR (`social_proof.py`)
- **Trigger:** Event-driven (NPS ≥ 8, referral made, 14 days active usage)
- **Steps:** send_testimonial_request → collect_response → request_permission → publish_to_site (update testimonials section via GitHub commit) → request_external_review (Google, Capterra) → update_aggregate_metrics ("X devis générés au Canada")

#### Agent 15: COMPETITOR WATCH (`competitor_watch.py`)
- **Trigger:** Cron weekly Wednesday 4AM
- **Steps:** scrape_competitor_sites (detect changes via hashing) → check_pricing_changes → check_product_hunt (new launches in category) → check_crunchbase (funding) → analyze_with_claude → alert_if_critical → log_report

#### Agent 16: FULFILLMENT OPS (`fulfillment.py`)
- **Trigger:** Event-driven (customer action via Supabase webhook)
- **Steps:** Dynamic per business type. Uses a registry pattern: `FULFILLMENT_HANDLERS = {"quote_os": QuoteOSHandler, "ar_collections": ARHandler, ...}`
- Each handler: receive_input → process_with_claude → generate_deliverable (PDF, email, etc.) → send_to_customer → track_status → handle_follow_ups

#### Agent 17: BILLING AGENT (`billing_agent.py`)
- **Trigger:** Stripe webhooks (via Hatchet webhook trigger)
- **Events handled:** customer.subscription.created, .updated, .deleted, invoice.payment_succeeded, invoice.payment_failed, charge.dispute.created, customer.subscription.trial_will_end (3 days before reverse trial ends)
- **Reverse trial handling:** When trial_will_end fires → send email "Your premium access ends in 3 days. Upgrade to keep [list features they used most]." At trial end → downgrade to free tier, NOT cancel. Show in-app what they're losing.
- **Payment recovery (see §7 above — up to 70% of failed payments are recoverable):**
  - Stripe Smart Retries: ENABLED (ML-optimized retry scheduling — free)
  - Stripe Card Account Updater: ENABLED (auto-updates expired cards — reduces hard declines 30-50%)
  - Stripe Adaptive Acceptance: ENABLED
  - Pre-dunning: email at 30/15/7 days BEFORE card expiry
  - Dunning: 4-email sequence over 14 days + in-app banner + SMS
  - Failed payment wall: restrict features (not full lockout) until payment updates
  - Multi-channel: email + in-app notification + SMS (not just email)
- **Canadian taxes:** TPS 5%, TVQ 9.975% QC, TVH 13-15% for ON/NB/NS/NL/PE. Use Stripe Tax for automatic calculation.

#### Agent 18: SUPPORT AGENT (`support_agent.py`)
- **Trigger:** Email IMAP trigger + in-app webhook + daily churn detection cron
- **Steps:** receive_message → search_knowledge_base (vector search or keyword) → generate_response (Claude Sonnet + RAG context) → send_response (in customer's language) → update_kb (add new Q&A pair) → check_churn_signals (daily: inactive >7d, usage drop >50%, unresolved tickets >48h)

#### Agent 19: UPSELL AGENT (`upsell_agent.py`)
- **Trigger:** Weekly cron + event-driven (usage threshold crossed)
- **Steps:** analyze_usage_per_customer → identify_upsell_opportunities (>80% quota, >3 months active, power referrer) → identify_cross_sell (customer matches ICP of another business) → generate_personalized_offer (Claude Haiku) → send_offer (max 1/month/customer) → track_conversion

#### Agent 20: ONBOARDING AGENT (`onboarding_agent.py`)
- **Trigger:** Event-driven (new signup) + daily check for stalled onboardings
- **Two modes:**
  - PRE-BUILD (spec mode): Generate onboarding spec for Builder (steps, copy FR/EN, aha moment definition, checklist items)
  - OPERATE mode: Track onboarding progress per customer. Send nudges if stalled (24h, 72h). Celebrate aha moment. Trigger Referral after activation.

#### Agent 21: ANALYTICS & KILL AGENT (`analytics_agent.py`)
- **Trigger:** Cron daily 11PM + weekly full report
- **Steps:** aggregate_stripe_data → aggregate_all_tables → calculate_metrics (MRR, churn, CAC, LTV, NPS) → calculate_kill_score (weighted formula) → save_snapshot → generate_report (Claude Sonnet) → send_to_slack → alert_anomalies
- **Kill score:** 0-100. Factors: MRR trend, customer trend, activation rate, churn rate, CAC payback, API margin, NPS. <30 after 8 weeks = recommend KILL.

#### Agent 22: SELF-REFLECTION (`self_reflection.py`)
- **Trigger:** Cron Sunday 3AM
- **Steps:** read_all_agent_logs (7 days) → read_all_error_logs → read_business_metrics → read_content_performance → analyze_with_opus (Claude Opus, biggest context) → categorize_findings (8 categories) → save_to_improvements → send_report_to_slack
- **8 categories:** recurring_error, missed_opportunity, inefficiency, blind_spot, cross_learning, drift, quality, new_idea
- **This agent uses Claude Opus** because it needs to synthesize across ALL agents and ALL businesses.

#### Agent 23: LEGAL GUARDRAIL (`legal_guardrail.py`)
- **Trigger:** Event-driven (content published, email template created, site deployed, BEFORE every voice call) + weekly full scan
- **Checks:** Privacy Policy present, Terms present, Cookie consent, CASL compliance (unsub link), no unsupported claims, Canadian tax display, Loi 101 FR content for QC, PIPEDA/Loi 25 data handling, no dark patterns in billing
- **VOICE/TELEPHONY COMPLIANCE (CRITICAL):**
  - **CRTC Unsolicited Telecommunications Rules:** All outbound calls must comply with CRTC regulations
  - **National Do Not Call List (DNCL/LNNTE):** EVERY outbound call number MUST be checked against the DNCL before dialing. Fine: up to $15,000 per non-compliant call for businesses. This is NON-NEGOTIABLE.
  - **DNCL subscription:** Must register with the CRTC DNCL operator (currently Bell Canada) and download the list. Cost: ~$55-2,740 CAD/year depending on area codes subscribed. Data must be refreshed every 31 days.
  - **Calling hours:** Outbound calls ONLY between 9:00 AM and 9:30 PM local time of the person being called (weekdays and Saturdays). No calls on Sundays or statutory holidays.
  - **Caller ID:** Must display a valid, callable return number. No spoofing.
  - **Opt-out:** If someone says "don't call me again" or "put me on your do not call list," add them to an internal DNC list IMMEDIATELY. Never call again.
  - **Internal DNC list:** Maintain a separate `internal_dncl` table for people who have asked not to be called, separate from the national DNCL. Must be checked BEFORE the national DNCL.
  - **AI disclosure:** When using an AI voice agent, there may be requirements to disclose that the caller is an AI. Check current CRTC guidance. At minimum, if asked "are you a robot?", the AI MUST answer honestly.
  - **Recording consent:** Canada is a one-party consent country federally, but some argue two-party is safer. At minimum, the AI should say "This call may be recorded for quality purposes" at the start.
- **Output:** Compliance issues with severity (critical/high/medium/low) + required fixes

#### Agent 24 (bonus): DEVOPS (`devops_agent.py`)
- **Trigger:** Cron every 5 minutes (health) + daily 2AM (backup)
- **Health:** HTTP check all services + Postgres + sites. Auto-restart Docker containers if down.
- **Backup:** pg_dump factory DB → compress → upload to S3/Backblaze B2. 30-day retention.
- **Monthly:** Test restore on temp DB.

#### Agent 25 (bonus): BUDGET GUARDIAN (`budget_guardian.py`)
- **Trigger:** Cron hourly + event-driven (cost threshold crossed)
- **Steps:** aggregate_api_costs (Anthropic usage API, Stripe fees, Sendgrid, Retell AI, Twilio, etc.) → check_against_limits → throttle_if_needed (reduce Claude model tier, pause non-critical agents, reduce call volume) → alert_meta
- **Hard limit:** $50/day total. If approaching → switch agents from Opus to Sonnet, Sonnet to Haiku. Reduce voice call volume first (most expensive per-unit).

#### Agent 26: VOICE AGENT (`voice_agent.py`)

**Trigger:** On-demand from Sales Agent (lead who REPLIED to cold email or SIGNED UP on landing page), Fulfillment Agent (payment follow-up for existing customers), Support Agent (inbound call), or Cron (scheduled callbacks for leads who requested one)

**⚠️ WARM CALLS ONLY (see CRITICAL DESIGN CHANGES §2).** This agent NEVER cold-calls. It only calls people who have demonstrated consent through one of: replying to an email, filling out a form, being an existing customer, or explicitly requesting a callback. This keeps us on the right side of CRTC ADAD rules without being paranoid.

**Claude model:** Handled by Retell AI (uses its own LLM integration), but Claude Sonnet for pre-call planning and post-call analysis.

**Voice platform:** Retell AI (recommended over Vapi — simpler API, $0.07/min all-in vs Vapi's $0.18-0.33/min effective cost). Telephony via Twilio (Canadian phone numbers).

**Steps DAG:**

1. `prepare_call` — Receive call request (lead_id or customer_id, call_type, business_id). Load lead/customer data from Postgres. Determine language (province → QC=FR, else=EN). Load the appropriate voice script from `voice_scripts` table.

2. `check_compliance` (CRITICAL — NEVER SKIP) — 
   a) Check consent type: lead must have status 'replied', 'signed_up', 'callback_requested', or be an existing customer. If status = 'new' or 'contacted' (never engaged) → ABORT. This is the warm-calls-only gate.
   b) Check `internal_dncl` table (people who asked not to be called) → if found, ABORT. Log reason.
   c) Check `dncl_cache` table → if found AND not expired, use cached result. If on DNCL, ABORT. Log reason.
   d) If not in cache OR expired → call DNCL lookup API → save to `dncl_cache` → if on DNCL, ABORT.
   d) Check calling hours: is it between 9:00 AM and 9:30 PM in the LEAD'S timezone? If not, schedule for next valid window.
   e) Check daily call volume limits per business (configurable, start conservative: max 30 calls/day).

3. `make_call` — Use Retell AI API to initiate the outbound call:
   - Set the agent's system prompt (from `voice_scripts`)
   - Set the greeting (first thing the AI says)
   - Set the voice (male/female, language FR/EN)
   - Set max duration (default 120 seconds for cold calls, 300 for support)
   - Pass context data (lead name, company, previous interactions)
   - Retell handles: STT → LLM → TTS in real-time
   - Retell webhook fires when call ends → triggers step 4

4. `process_call_result` — Receive Retell webhook with call data:
   - Save transcript to `voice_calls` table
   - Use Claude Sonnet to analyze transcript: extract outcome (interested/not_interested/callback/meeting_booked/wrong_number/do_not_call)
   - If outcome = "meeting_booked" → create Calendly booking or send confirmation email
   - If outcome = "interested" → update lead status in Postgres, trigger Email Nurture with personalized follow-up
   - If outcome = "callback_requested" → schedule a callback (create delayed Hatchet workflow)
   - If outcome = "do_not_call" → add to `internal_dncl` IMMEDIATELY
   - If outcome = "not_interested" → mark lead as lost, do NOT call again
   - If outcome = "voicemail" → optionally leave a voicemail via Retell, then continue email sequence

5. `log_and_optimize` — Log everything to `voice_calls` and `agent_logs`. Track metrics per script variant for A/B testing. Calculate cost per connected call, cost per meeting booked.

**Voice Scripts (stored in `voice_scripts` table, managed per business):**

COLD CALL — QUALIFICATION (FR, Quote OS example):
```
System prompt for voice AI:
Tu es un représentant de Toîturo, un logiciel de soumission pour couvreurs au Québec. Tu appelles des entrepreneurs en couverture pour leur présenter le produit. 

CONTEXTE DU LEAD: {lead_name}, {company_name}, {city}, {any_known_details}

TON APPROCHE:
- Sois professionnel mais chaleureux. Tutoie si l'interlocuteur est clairement un entrepreneur terrain.
- L'appel doit durer MAXIMUM 90 secondes.
- Tu n'es PAS un vendeur agressif. Tu poses des questions.

SCRIPT:
1. INTRO (10 sec): "Bonjour {lead_name}, c'est [nom] de Toîturo. Est-ce que je vous dérange?"
   - Si "oui" → "Pas de problème, quand est-ce qu'un bon moment pour vous rappeler?" → book callback → END
   - Si "non" / silence → continue

2. HOOK (15 sec): "On aide les couvreurs au Québec à faire leurs soumissions 5 fois plus vite. En ce moment, comment vous faites vos estimations? Excel, papier, autre logiciel?"
   - ÉCOUTE la réponse. C'est la partie la plus importante.

3. QUALIFY (20 sec): "Combien de soumissions vous faites par mois à peu près?"
   - Si > 10/mois → HOT LEAD
   - Si < 5/mois → probablement pas le bon fit, mais continue poliment

4. CTA (15 sec): 
   - Si intéressé: "Est-ce que je peux vous envoyer une vidéo de 3 minutes qui montre comment ça marche? Quel est le meilleur email?"
   - Si hésitant: "Pas de pression. Je vous envoie juste l'info par email et vous regardez quand ça vous convient."
   - Si pas intéressé: "Pas de problème, merci pour votre temps. Bonne journée!"

5. CLOSE (10 sec): Confirmer l'email, remercier, raccrocher.

RÈGLES:
- Si on te demande "es-tu un robot?" → "Je suis un assistant IA de Toîturo. Est-ce que vous préférez qu'on vous rappelle avec une vraie personne?"
- Si on te dit "ne m'appelez plus" → "C'est noté, on vous retire de notre liste immédiatement. Désolé du dérangement."
- JAMAIS mentir sur qui tu es
- JAMAIS être insistant si la personne dit non
- TOUJOURS "Cet appel peut être enregistré pour des fins de qualité"
```

COLD CALL — QUALIFICATION (EN, same structure adapted for English Canadian market)

PAYMENT FOLLOW-UP (FR, AR Collections example):
```
System prompt:
Tu appelles un client de {business_name} pour un suivi de paiement. La facture #{invoice_number} de {amount} CAD est en retard de {days_overdue} jours.

APPROCHE: Amical mais professionnel. Ce n'est PAS du harcèlement. C'est un rappel courtois.

1. INTRO: "Bonjour {contact_name}, c'est [nom] qui appelle au nom de {business_name}. Comment allez-vous?"
2. MENTION: "Je vous appelle au sujet de la facture #{invoice_number} de {amount}$. On n'a pas encore reçu le paiement. Est-ce qu'il y a eu un problème?"
3. ÉCOUTE: Laisse la personne expliquer. Ne coupe pas.
4. RÉSOLUTION:
   - Si "j'ai oublié" → "Pas de problème! Je peux vous envoyer le lien de paiement par texto ou email tout de suite."
   - Si "difficultés financières" → "On comprend. Est-ce qu'un plan de paiement serait utile? Je peux en discuter avec {business_name}."
   - Si "contestation" → "Je comprends. Je vais transmettre ça à {business_name} pour qu'ils vous recontactent directement."
5. CLOSE: Confirmer les prochaines étapes. Remercier.

Max 120 secondes. Ton chaleureux.
```

INBOUND SUPPORT:
```
System prompt:
Tu es l'assistant téléphonique de {business_name}. Tu réponds aux questions des clients existants.

Tu as accès à la base de connaissances suivante:
{knowledge_base_context}

RÈGLES:
- Identifie le client par son nom ou numéro de compte
- Réponds aux questions simples directement
- Pour les questions complexes: "Je vais noter votre question et quelqu'un de l'équipe vous rappelle dans les 2 heures."
- Pour les urgences techniques: "Je transfere votre appel" (escalade vers Slack)
- Toujours confirmer: "Est-ce que ça répond à votre question?"
- Max 5 minutes par appel
```

**Retell AI Integration (`retell_client.py`):**
```python
# src/integrations/retell_client.py
import httpx
from src.config import settings

BASE_URL = "https://api.retellai.com"

headers = {
    "Authorization": f"Bearer {settings.RETELL_API_KEY}",
    "Content-Type": "application/json",
}

async def create_agent(name: str, system_prompt: str, voice_id: str, language: str) -> dict:
    """Create a Retell voice agent for a specific business/call type."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/create-agent", headers=headers, json={
            "agent_name": name,
            "response_engine": {
                "type": "retell-llm",
                "llm_id": settings.RETELL_LLM_ID,  # Or use custom LLM
            },
            "voice_id": voice_id,  # French or English voice
            "language": language,
            "general_prompt": system_prompt,
            "begin_message": "",  # Set per-call in create_call
            "max_call_duration": 120,
        })
        return r.json()

async def create_call(agent_id: str, to_number: str, from_number: str, metadata: dict, greeting: str) -> dict:
    """Initiate an outbound call."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/v2/create-phone-call", headers=headers, json={
            "agent_id": agent_id,
            "to_number": to_number,        # E.164: +15145551234
            "from_number": from_number,     # Your Twilio Canadian number
            "metadata": metadata,           # {lead_id, business_id, call_type}
            "retell_llm_dynamic_variables": {
                "lead_name": metadata.get("lead_name", ""),
                "company_name": metadata.get("company_name", ""),
                "context": metadata.get("context", ""),
            },
            "begin_message": greeting,
        })
        return r.json()

async def get_call(call_id: str) -> dict:
    """Get call details including transcript."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/v2/get-call/{call_id}", headers=headers)
        return r.json()
```

**DNCL Client (`dncl_client.py`):**
```python
# src/integrations/dncl_client.py
"""
Canada National Do Not Call List (DNCL/LNNTE) integration.

IMPORTANT: You must register with the CRTC DNCL operator and subscribe
to download the list for the area codes you're calling.
Registration: https://lnnte-dncl.gc.ca/
Cost: $55 - $2,740 CAD/year depending on area codes.

The DNCL data is downloaded as a file and loaded into our dncl_cache table.
It MUST be refreshed every 31 days per CRTC rules.
"""
import csv
from datetime import datetime, timedelta
from src.db import SessionLocal

async def check_dncl(phone_number: str) -> bool:
    """
    Check if a phone number is on the DNCL.
    Returns True if the number IS on the DNCL (do NOT call).
    Returns False if the number is NOT on the DNCL (ok to call).
    """
    db = SessionLocal()
    try:
        # Check cache first
        result = db.execute(
            "SELECT on_dncl, expires_at FROM dncl_cache WHERE phone_number = :phone",
            {"phone": phone_number}
        ).fetchone()
        
        if result and result.expires_at > datetime.utcnow():
            return result.on_dncl
        
        # If not in cache or expired, check against the downloaded DNCL file
        # The DNCL file should be downloaded monthly and loaded into the DB
        # For now, if not in cache, assume NOT on DNCL but flag for manual check
        on_dncl = _lookup_in_dncl_file(phone_number)
        
        # Cache the result (expires in 30 days per CRTC rules)
        db.execute(
            """INSERT INTO dncl_cache (phone_number, on_dncl, checked_at, expires_at)
               VALUES (:phone, :on_dncl, NOW(), NOW() + INTERVAL '30 days')
               ON CONFLICT (phone_number) DO UPDATE SET on_dncl = :on_dncl, checked_at = NOW(), expires_at = NOW() + INTERVAL '30 days'""",
            {"phone": phone_number, "on_dncl": on_dncl}
        )
        db.commit()
        return on_dncl
    finally:
        db.close()

async def check_internal_dncl(phone_number: str) -> bool:
    """Check our internal DNC list (people who asked not to be called)."""
    db = SessionLocal()
    try:
        result = db.execute(
            "SELECT 1 FROM voice_calls WHERE phone_number = :phone AND outcome = 'do_not_call' LIMIT 1",
            {"phone": phone_number}
        ).fetchone()
        return result is not None
    finally:
        db.close()

async def add_to_internal_dncl(phone_number: str, reason: str = "requested"):
    """Add a number to our internal DNC list."""
    db = SessionLocal()
    try:
        # We use the voice_calls table with outcome='do_not_call' as our internal list
        db.execute(
            """INSERT INTO voice_calls (phone_number, call_type, status, outcome, direction, business_id)
               VALUES (:phone, 'do_not_call_request', 'completed', 'do_not_call', 'outbound', NULL)
               ON CONFLICT DO NOTHING""",
            {"phone": phone_number}
        )
        db.commit()
    finally:
        db.close()

def _lookup_in_dncl_file(phone_number: str) -> bool:
    """Look up a number in the downloaded DNCL CSV file."""
    # The DNCL file is downloaded monthly from the CRTC portal
    # and stored at /data/dncl/current_dncl.csv
    # Format: phone numbers in E.164 or 10-digit format
    try:
        with open("/data/dncl/current_dncl.csv", "r") as f:
            reader = csv.reader(f)
            stripped = phone_number.replace("+1", "").replace("-", "").replace(" ", "")
            for row in reader:
                if row and row[0].replace("-", "").replace(" ", "") == stripped:
                    return True
        return False
    except FileNotFoundError:
        # DNCL file not downloaded yet — CRITICAL: must be downloaded before making calls
        raise RuntimeError("DNCL file not found at /data/dncl/current_dncl.csv. Cannot make outbound calls without DNCL data.")
```

**Twilio Setup (for Canadian phone numbers):**
```python
# src/integrations/twilio_client.py
"""
Twilio is used for:
1. Purchasing Canadian phone numbers (+1 514, +1 416, +1 604, etc.)
2. Connecting Retell AI to the PSTN (public phone network)
3. SMS for appointment reminders and payment links

Each business gets its own Twilio phone number for local presence.
QC businesses → 514/438 number. ON businesses → 416/647. etc.
"""
import httpx
from src.config import settings

async def buy_phone_number(area_code: str) -> dict:
    """Buy a Canadian phone number in a specific area code."""
    async with httpx.AsyncClient() as client:
        # Search for available numbers
        r = await client.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/AvailablePhoneNumbers/CA/Local.json",
            params={"AreaCode": area_code, "VoiceEnabled": True, "SmsEnabled": True},
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        )
        numbers = r.json().get("available_phone_numbers", [])
        if not numbers:
            raise RuntimeError(f"No available numbers for area code {area_code}")
        
        # Purchase the first available number
        chosen = numbers[0]["phone_number"]
        r = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers.json",
            data={"PhoneNumber": chosen},
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        )
        return r.json()
```

#### Agent 27: GROWTH HACKER (`growth_hacker.py`)

**Trigger:** Cron weekly (Tuesday 6AM) + On-demand from Meta Orchestrator when a business is stuck (<5% MRR growth for 2+ weeks)

**Claude model:** claude-opus-4-20250514 (needs creative reasoning + research synthesis)

**Purpose:** This agent does NOT do SEO, cold email, or social posting — the other agents handle that. This agent finds and executes the non-obvious, high-leverage, often one-time tactics that create outsized results. It thinks like a founder at 2AM asking "what if we tried..."

**Steps DAG:**

1. `research_opportunities` — For each active business, research:
   - **Marketplace infiltration:** Find marketplaces, directories, and aggregators where the ICP already shops. Examples: Shopify App Store, WordPress plugin directory, QuickBooks App Store, Capterra, G2, GetApp, SaaSWorthy, Product Hunt, BetaList, AppSumo. For trades specifically: HomeStars, Houzz, Rénoquébec, provincial contractor directories.
   - **Integration parasitism:** Find popular tools the ICP already uses. Build a free integration/plugin for them. Example: Quote OS could be a "Generate quote from photo" plugin for a popular contractor management app. The plugin is free but funnels users to the full product.
   - **Data-as-marketing:** Identify datasets that could be generated from the product's domain and published for free. Example: "Average roofing costs by Quebec city — 2026 data" → publish as a free report → journalists and bloggers link to it → SEO + authority. AR Collections could publish "Average payment delays by industry in Canada."
   - **Community hijacking:** Find dying or underserved communities/forums/Facebook Groups in the niche. Can we take over as admin? Can we create THE definitive community for this niche and funnel to the product?
   - **Event piggybacking:** Find upcoming industry events, conferences, trade shows, webinars. Can we sponsor a tiny part? Can we host a side-event? Can we just show up with business cards? For trades: APCHQ events, regional construction expos, CCQ meetings.
   - **Strategic partnerships:** Identify complementary businesses (not competitors) who serve the same ICP. Example: Quote OS + roofing material supplier → they recommend our software to their clients in exchange for a referral fee or integration.
   - **Template/tool bait:** Create a genuinely useful free tool or template that the ICP would Google for. Example: "Free roofing estimate calculator" landing page → captures email → nurtures to paid product. "Free late payment notice template" for AR Collections.
   - **Reverse engineering competitor traffic:** Use SimilarWeb, Ahrefs (via API or scraping) to see where competitors get traffic. Replicate what works, ignore what doesn't.
   - **Piggyback on regulations:** When a new regulation passes (like the OQLF rules for bilingual labeling), create the definitive guide/tool to comply. Compliance Ops could own "How to comply with the June 2025 OQLF changes" and capture every brand searching for it.
   - **Micro-influencer seeding:** Find 10-20 micro-influencers in the niche (not marketing influencers — actual contractors, accountants, property managers with small followings). Offer free lifetime access in exchange for an honest review/post.
   - **Government/association listings:** Get listed in government directories (BDC, CDAP, provincial business tools directories). Many trades search for tools through their professional associations.
   - **Trigger-based outreach:** Monitor specific events that signal buying intent. Example: new business registrations (Registraire des entreprises du Québec) → these are new contractors who need software. Building permits issued → contractors who just got a project and need to quote.

2. `score_and_prioritize` — For each tactic found, Claude Opus scores on:
   - Effort (1-10, lower is less effort)
   - Potential impact (1-10, higher is better)
   - Cost ($0 to $500 max)
   - Time to result (days)
   - Repeatability (one-time vs recurring)
   - Calculate: Impact × Repeatability / (Effort × Cost factor) = priority score

3. `auto_execute_easy_wins` — Tactics scoring above threshold AND requiring only API calls (no human intervention) are executed immediately:
   - Submit to directories (automated form filling via HTTP requests)
   - Create free tool landing pages (trigger Builder for a micro-project)
   - Publish data reports (trigger Content Engine with specific data-driven format)
   - Set up trigger-based monitoring (create a Hatchet cron workflow for new business registrations, building permits, etc.)
   - Request listings in app marketplaces (automated application submission)

4. `propose_complex_tactics` — Tactics requiring human involvement or significant investment are written up as proposals:
   - Partnership outreach drafts → Slack for review
   - Event sponsorship opportunities → Slack with cost/benefit
   - Integration/plugin build specs → sent to Builder as a feature request
   - Community creation/takeover plans → Slack for approval

5. `track_and_learn` — For each tactic executed:
   - Track traffic source in Plausible (UTM tags per tactic)
   - Track signups attributed to each tactic
   - After 30 days: measure actual CAC per tactic
   - Feed results back into scoring model
   - Kill tactics with 0 results after 30 days
   - Double-down budget on tactics that work

**System prompt:** (save as `prompts/growth_hacker.txt`)
```
Tu es le Growth Hacker Agent. Ton job est de trouver des méthodes NON-CONVENTIONNELLES pour acquérir des clients.

Tu ne fais PAS: SEO (Content Engine le fait), cold email (Sales Agent le fait), social media posting (Social Agent le fait), referral (Referral Agent le fait), voice calling (Voice Agent le fait).

Tu fais: tout le reste. Les trucs créatifs. Les hacks. Les raccourcis. Les choses auxquelles personne ne pense.

Tu reçois pour chaque business:
- Le Scout Report (niche, ICP, competitors)
- Les métriques actuelles (MRR, growth rate, top acquisition channels)
- Les tactiques déjà testées et leurs résultats

TON MINDSET:
- Un couvreur au Québec ne cherche pas "SaaS de soumission". Il cherche "calculer prix toiture" ou "modèle soumission couvreur gratuit" ou il va sur le site de la APCHQ.
- Un proprio ne cherche pas "rent management software". Il google "lettre de retard de loyer modèle" ou "comment expulser locataire québec".
- PENSE comme le client, pas comme un marketeur.
- Les meilleures tactiques coûtent $0 et exploitent un canal que les concurrents ignorent.

CATÉGORIES DE TACTIQUES À EXPLORER:
1. MARKETPLACE INFILTRATION: Se faire lister partout où l'ICP cherche des outils
2. INTEGRATION PARASITISM: Devenir plugin/extension d'un outil populaire existant
3. DATA-AS-MARKETING: Publier des données uniques que les journalistes/blogueurs veulent citer
4. COMMUNITY OWNERSHIP: Créer ou prendre le contrôle de la communauté #1 de la niche
5. EVENT PIGGYBACKING: Être présent aux événements industrie sans payer le gros prix
6. STRATEGIC PARTNERSHIPS: S'allier avec des businesses complémentaires
7. TEMPLATE/TOOL BAIT: Offrir un outil gratuit qui résout 20% du problème → funnel vers le produit payant
8. COMPETITOR TRAFFIC HIJACK: Aller chercher les clients mécontents du concurrent
9. REGULATION SURFING: Capitaliser sur les nouvelles réglementations (OQLF, PIPEDA, etc.)
10. MICRO-INFLUENCER SEEDING: Donner le produit gratuit à 20 personnes influentes dans la niche
11. GOVERNMENT LISTINGS: Se faire lister dans les répertoires gouvernementaux et associatifs
12. TRIGGER-BASED OUTREACH: Détecter les événements qui signalent un besoin immédiat

POUR CHAQUE BUSINESS, produis:
{
  "business_id": X,
  "tactics": [
    {
      "name": "string",
      "category": "1-12 from above",
      "description": "what to do exactly, step by step",
      "effort_score": 1-10,
      "impact_score": 1-10,
      "cost_estimate_cad": 0-500,
      "time_to_result_days": N,
      "repeatability": "one_time | monthly | ongoing",
      "auto_executable": true/false,
      "execution_steps": ["step 1", "step 2", ...],
      "priority_score": calculated,
      "canadian_specific": true/false,
      "language": "fr | en | both"
    }
  ],
  "top_3_immediate": ["tactic names that should be executed this week"],
  "top_3_proposals": ["tactic names that need human approval"]
}

CRITIQUE: Ne propose JAMAIS de tactiques illégales, spammy, ou qui pourraient nuire à la réputation de la marque. Chaque tactique doit être quelque chose dont on serait fier si un journaliste l'apprenait.
```

**Per-business tactic examples (to seed the agent's thinking):**

QUOTE OS (couvreurs):
- Publish "Coûts moyens de toiture par ville au Québec — Données 2026" as a free report
- Create a free "Calculateur de toiture" web tool (→ email capture → nurture)
- Get listed on HomeStars, Houzz, and APCHQ's tool directory
- Monitor new construction business registrations at REQ → auto-outreach within 48h
- Partner with roofing material suppliers (BMR, Patrick Morin, etc.) to recommend the software
- Build a free QuickBooks/Xero export feature → list on their app marketplaces
- Create "Les 10 erreurs de soumission qui coûtent cher aux couvreurs" → viral in niche FB groups

AR COLLECTIONS:
- Publish "Délais de paiement moyens par industrie au Canada — 2026" → press coverage
- Create free "Modèle de lettre de recouvrement" PDF → SEO lead magnet
- Get listed in QuickBooks/Xero app stores as a "collections add-on"
- Partner with bookkeepers/CPAs who see the problem daily
- Monitor companies posting "accounts receivable" job listings → they have a pain point

COMPLIANCE OPS:
- Create THE definitive guide to OQLF June 2025 compliance → capture every US brand searching
- Build a free "Compliance checker" that scans a Shopify store's FR content → shows gaps → upsell full audit
- Partner with cross-border shipping companies (eShipper, Purolator, etc.)
- Get listed on Canada Business Network and CDAP directories

---

## CEO DASHBOARD (`src/dashboard/`)

The dashboard is your ONLY interface with the factory. Everything else is autonomous. If you can't see it on the dashboard, it doesn't exist.

**Tech stack:** FastAPI + HTMX + Tailwind (server-rendered, fast, no React build step needed). Runs as a separate service in Docker Compose on port 9000. Protected by basic auth or Cloudflare Access.

**Add to docker-compose.yml:**
```yaml
  # ── CEO Dashboard ──
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    restart: always
    depends_on:
      - postgres
    ports:
      - "9000:9000"
    environment:
      DATABASE_URL: postgres://factory:${POSTGRES_PASSWORD}@postgres:5432/factory
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
      DASHBOARD_USER: ${DASHBOARD_USER}
      DASHBOARD_PASSWORD: ${DASHBOARD_PASSWORD}
      HATCHET_API_URL: http://hatchet-engine:8080
```

### Dashboard Pages:

**0. SETUP WIZARD (first-time only — `/setup`)**
If the `secrets` table is empty (first boot), redirect ALL routes here. This is how you onboard the factory without touching .env:

Step 1: "Core" (required to do anything)
- Anthropic API Key — paste + test button (calls /v1/models to verify)
- Serper API Key — paste + test
- Slack Webhook URL — paste + test (sends a "Factory connected!" message)

Step 2: "Lead Generation" (required for Distribution Engine)
- Apollo API Key — paste + test
- Hunter API Key — paste + test
- ZeroBounce API Key — paste + test

Step 3: "Infrastructure" (required to create businesses)
- Namecheap API Key + API User + Server IP
- Cloudflare API Token
- Vercel Token
- GitHub Token
- Supabase Access Token
- Stripe Secret Key (show test/live badge based on prefix)
- Registrant info (name, address, phone, email for domain purchases)

Step 4: "Outreach" (required to send emails/calls)
- Instantly API Key
- Resend API Key
- Twilio Account SID + Auth Token
- Retell API Key
- Reddit credentials

Step 5: "Optional" (enhance but not required)
- SparkToro API Key
- Syften API Key
- DataForSEO API Key
- Google Ads credentials
- Meta Ads credentials
- Hetzner S3 credentials (backups)

Each step has: paste field, "Test connection" button (green check or red X), and "Save & continue" button. You can skip steps and come back later. The dashboard shows which integrations are connected vs missing on the Overview page.

**7. SETTINGS (`/settings`)**
- All API keys organized by category (same as setup wizard, but editable anytime)
- Each key shows: masked value (last 4 chars), connection status (green/red), last tested date
- "Test all connections" button — runs health check on every configured service
- Factory config: timezone, daily budget limit, voice call limit, dashboard password
- Registrant info for domain purchases
- DRY_RUN toggle (master switch)
- Danger zone: "Reset factory" (wipe all data), "Export all data" (pg_dump)

### Secrets Storage Architecture:

```sql
-- Add to migrations
CREATE TABLE secrets (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,          -- e.g. 'ANTHROPIC_API_KEY', 'STRIPE_SECRET_KEY'
    value_encrypted TEXT NOT NULL,      -- AES-256-GCM encrypted
    category TEXT NOT NULL,             -- 'core', 'lead_gen', 'infrastructure', 'outreach', 'optional'
    display_name TEXT,                  -- 'Anthropic API Key'
    is_configured BOOLEAN DEFAULT FALSE,
    last_tested_at TIMESTAMPTZ,
    last_test_status TEXT,             -- 'ok', 'failed', 'untested'
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Encryption:** AES-256-GCM using a master key. The ONLY thing in .env is:
```bash
# .env — THIS IS ALL YOU NEED
POSTGRES_PASSWORD=your_db_password
ENCRYPTION_KEY=your_32_byte_hex_key    # openssl rand -hex 32
DASHBOARD_USER=ceo
DASHBOARD_PASSWORD=your_password
```

The `ENCRYPTION_KEY` encrypts/decrypts all secrets in the DB. Generate it once: `openssl rand -hex 32`.

**How config.py changes:**
```python
# src/config.py — reads from DB, falls back to .env for backwards compat
from cryptography.fernet import Fernet  # or use AES-GCM directly
import os

class Settings:
    def __init__(self):
        self._cache = {}
        self._db_url = os.environ["DATABASE_URL"]
        self._encryption_key = os.environ["ENCRYPTION_KEY"]
    
    def get(self, key: str) -> str | None:
        """Get a secret. Checks DB first, falls back to env var."""
        if key in self._cache:
            return self._cache[key]
        
        # Try DB
        value = self._get_from_db(key)
        if value:
            self._cache[key] = value
            return value
        
        # Fallback to .env (for backwards compat or boot-time vars)
        value = os.environ.get(key)
        if value and value != "...":
            return value
        
        return None
    
    def _get_from_db(self, key: str) -> str | None:
        # Query secrets table, decrypt value
        row = db.execute("SELECT value_encrypted FROM secrets WHERE key = :key", {"key": key}).fetchone()
        if row:
            return decrypt(row.value_encrypted, self._encryption_key)
        return None

settings = Settings()

# Usage in any agent:
# api_key = settings.get("ANTHROPIC_API_KEY")
```

**Every agent uses `settings.get("KEY_NAME")` instead of `os.environ["KEY_NAME"]`.** This means:
1. First boot: .env has 4 lines. Dashboard redirects to setup wizard.
2. You paste API keys in the browser. They get encrypted and stored in Postgres.
3. Agents read keys from the DB via `settings.get()`.
4. You never SSH into the server to edit .env again.

**1. OVERVIEW (home page — `/`)**
- Total MRR across all businesses (big number, trend arrow)
- Total customers (active, new this week, churned this week)
- Total leads in pipeline
- API spend today / this month / budget remaining
- Factory health: green/yellow/red per service (Postgres, Hatchet, all business sites, Retell, email)
- Agent activity: how many workflows ran today, success rate
- Self-Reflection last findings (top 3)
- Quick action buttons: "Run Idea Factory now", "Run Self-Reflection now"

**2. PER-BUSINESS DEEP DIVE (`/business/{slug}`)**
- MRR chart (daily, 30-day trend)
- Customer count chart
- Churn rate (weekly trend)
- Kill score gauge (0-100, color-coded)
- Acquisition funnel: leads → contacted → replied → converted (with conversion rates)
- Top acquisition channels (pie chart: SEO, cold email, voice, social, referral)
- Content performance: top 5 articles by traffic
- Voice calling stats: calls made, connect rate, meetings booked
- Recent support tickets
- Recent agent activity for this business
- **CONTROLS:**
  - Slider: daily API budget for this business ($0-100)
  - Slider: daily cold email volume (0-500)
  - Slider: daily voice call volume (0-50)
  - Toggle: pause/resume outbound for this business
  - Button: "Kill this business" (with confirmation)
  - Button: "Double down" (2x budget allocation)

**3. AGENT PERFORMANCE (`/agents`)**
- Table: all 27 agents, last run time, success rate (7 days), average cost per run, total cost this month
- Click into any agent → see last 50 executions with status, duration, cost, input/output summary
- Error log: all agent errors in last 7 days, sorted by recency
- Self-Reflection proposals: list of improvements with status (proposed/approved/implemented/rejected)
  - **CONTROLS:** Approve/reject buttons on each proposal

**4. BUDGET & COSTS (`/budget`)**
- Daily API cost breakdown (stacked bar chart: Anthropic, Sendgrid, Instantly, Retell, Twilio, Namecheap, Vercel)
- Monthly cost projection based on current run rate
- Cost per customer acquired (by business)
- Cost per voice call connected
- Budget allocation per business (editable pie chart)
- **CONTROLS:**
  - Set daily total budget cap ($)
  - Set per-business budget allocation (% or fixed $)
  - Set Claude model tier per agent (Opus/Sonnet/Haiku dropdown)
  - Emergency: "Throttle all agents to Haiku" button
  - Emergency: "Pause all non-essential agents" button

**5. DECISIONS (`/decisions`)**
- Businesses in validation: metrics dashboard, GO/KILL buttons
- Kill score alerts: businesses approaching <30 threshold
- Pending human actions: things agents have escalated to you
- Upcoming: businesses ready for next phase (e.g., "AR Collections passed validation, ready for build")
- History: all kill/go/scale decisions with outcome

**6. IDEA PIPELINE (`/ideas`)**
- All ideas with scores, status, scout reports
- Click into any idea → read full Scout Report
- Quick actions: "Send to Scout", "Send to Validator", "Archive"

### Dashboard Data Sources:
All data comes from Postgres tables. The dashboard does NOT call external APIs — it reads the data that agents have already written:
- `daily_snapshots` → charts and trends
- `businesses` → status, MRR, kill score
- `customers` → counts and churn
- `leads` → pipeline funnel
- `agent_logs` → agent performance
- `improvements` → self-reflection proposals
- `voice_calls` → voice stats
- `budget_tracking` → cost data
- `content` → content performance
- `support_tickets` → support volume
- `ideas` → idea pipeline
- `secrets` → settings page (API keys, connection status)

### Dashboard Controls write to:
- `businesses.config` → budget allocation, volume limits, pause state
- `improvements.status` → approve/reject proposals
- `ideas.status` → advance ideas through pipeline
- Also triggers Hatchet workflows directly via API (e.g., "Run Idea Factory now" → `hatchet.client.admin.run_workflow("idea-factory")`)

---

## GEO (GENERATIVE ENGINE OPTIMIZATION) + llms.txt

This is NOT a separate agent — it's built into the Content Engine (Agent 9) and the Builder (Agent 7) as additional responsibilities. Every business site must be optimized for AI discoverability from day one.

### What the Builder must implement in EVERY business site:

**1. `/llms.txt` file (root of every site):**
```markdown
# [Business Name]

> [One-line description of the business]. Canadian SaaS serving [niche] across Canada. Bilingual FR/EN.

## Key Pages
- [Pricing](/en/pricing): Plans, features, and pricing in CAD
- [Features](/en/features): Complete feature overview
- [How it Works](/en/how-it-works): Step-by-step explanation of the product
- [About](/en/about): Company background, Canadian-made, team
- [FAQ](/en/faq): Frequently asked questions and answers
- [Blog](/en/blog): Industry insights and guides for [niche]

## Documentation
- [Getting Started](/en/docs/getting-started): How to set up your account
- [API Reference](/en/docs/api): API documentation (if applicable)

## Optional
- [Changelog](/en/changelog): Recent product updates
- [Case Studies](/en/case-studies): Customer success stories
- [Comparisons](/en/compare): How we compare to alternatives
```

**2. `/llms-full.txt` — complete site content flattened:**
Auto-generated on every deploy. Takes ALL pages, strips HTML, outputs clean Markdown into a single file. The Content Engine updates this after every new article published.

**3. Markdown versions of every page:**
Every page at `/en/pricing` should also be available at `/en/pricing.md` (or equivalent clean-text version). This is trivial in Next.js — add a route that renders the page content as Markdown instead of HTML.

**4. Schema.org structured data on every page:**
- `Organization` schema on homepage (name, URL, logo, founded, location: Canada)
- `Product` schema on pricing/features (name, description, offers with CAD pricing)
- `Article` schema on blog posts (headline, author, datePublished, dateModified)
- `FAQPage` schema on FAQ
- `Review` schema on testimonials
- `LocalBusiness` schema if applicable

**5. robots.txt that ALLOWS AI crawlers:**
```
User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Applebot-Extended
Allow: /

Sitemap: https://[domain]/sitemap.xml
```

### What the Content Engine must do for GEO:

**6. Write content optimized for AI citation, not just Google ranking:**
- Every article should contain clear, quotable statements that an LLM would want to cite
- Include specific data points, statistics, and numbers (LLMs love citing specific numbers)
- Structure with clear H2/H3 headers that match questions people ask LLMs
- Include a "Key Takeaways" or "Quick Answer" section at the top of each article
- Example: Instead of "Roofing costs vary depending on many factors", write "The average cost of re-roofing a 1,500 sq ft house in Quebec in 2026 is $8,500-$14,000 CAD, with asphalt shingles at $4.50-$7.00/sq ft installed."
- LLMs cite SPECIFIC content. Generic content gets ignored.

**7. Target "question" keywords that people ask LLMs:**
- Traditional SEO targets "best roofing software"
- GEO targets "What's the best way for a Quebec roofer to estimate a job?" — the kind of question someone would ask ChatGPT or Perplexity
- The Content Engine should research: what questions do people ask Claude/ChatGPT about this niche? Then create the definitive answer.

**8. Entity positioning:**
- Ensure the business name appears in context with the niche and "Canada" across multiple pages
- Example: "Toîturo is a Canadian soumission management platform for couvreurs" should appear naturally across the site
- This helps LLMs associate the brand with the niche + geography

**9. Comparison and "best of" pages:**
- Create pages like "Best Roofing Estimation Software in Canada (2026)"
- LLMs frequently cite comparison/list articles
- Include your product naturally (not as #1 — that's transparent) alongside real alternatives

**10. Freshness signals:**
- Update key pages (pricing, features, homepage) at least monthly with visible "Last updated: [date]"
- LLMs and AI search engines prefer recently updated content
- The Content Engine should have a monthly "refresh key pages" task

**11. Be the source of truth for your niche in Canada:**
- If someone asks Claude "What tools do Canadian roofers use for estimates?", your content should be comprehensive enough to be THE answer
- Publish original data, surveys, and insights that only you have
- The Growth Hacker's "data-as-marketing" tactic feeds directly into GEO

### GEO Metrics (tracked by Analytics Agent):
- AI referral traffic in Plausible (identify GPTBot, ClaudeBot, PerplexityBot referrers)
- Brand mentions in AI-generated responses (periodic manual or automated checks via Perplexity/ChatGPT API)
- /llms.txt access in server logs (who's reading it?)
- Structured data validation (Google Rich Results Test)

---

## LLM WRAPPER (`llm.py`)

```python
import anthropic
from src.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

MODEL_TIERS = {
    "opus": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

async def call_claude(
    model: str = "sonnet",
    system: str = "",
    user: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    """Unified Claude API wrapper. Tracks costs in DB."""
    
    model_id = MODEL_TIERS.get(model, model)
    
    messages = [{"role": "user", "content": user}]
    
    kwargs = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    
    response = client.messages.create(**kwargs)
    
    # Track cost (approximate)
    input_cost = response.usage.input_tokens * _get_input_price(model_id)
    output_cost = response.usage.output_tokens * _get_output_price(model_id)
    total_cost = input_cost + output_cost
    
    # Log cost to DB (async, non-blocking)
    _log_cost(model_id, response.usage.input_tokens, response.usage.output_tokens, total_cost)
    
    text = response.content[0].text
    
    if json_mode:
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
    
    return text


def _get_input_price(model_id: str) -> float:
    """Price per token (approximate, update as needed)"""
    if "opus" in model_id: return 15.0 / 1_000_000
    if "sonnet" in model_id: return 3.0 / 1_000_000
    if "haiku" in model_id: return 0.80 / 1_000_000
    return 3.0 / 1_000_000

def _get_output_price(model_id: str) -> float:
    if "opus" in model_id: return 75.0 / 1_000_000
    if "sonnet" in model_id: return 15.0 / 1_000_000
    if "haiku" in model_id: return 4.0 / 1_000_000
    return 15.0 / 1_000_000
```

---

## INTEGRATIONS PATTERN

Each integration is a thin wrapper around the API. Example:

```python
# src/integrations/namecheap_client.py
import httpx
from src.config import settings

BASE_URL = "https://api.namecheap.com/xml.response"

# Cloudflare nameservers — all domains point here immediately
CF_NAMESERVERS = ["cody.ns.cloudflare.com", "jada.ns.cloudflare.com"]  # Replace with your actual CF nameservers

async def check_domain(domain: str) -> bool:
    """Check if a domain is available."""
    async with httpx.AsyncClient() as client:
        r = await client.get(BASE_URL, params={
            "ApiUser": settings.NAMECHEAP_API_USER,
            "ApiKey": settings.NAMECHEAP_API_KEY,
            "UserName": settings.NAMECHEAP_API_USER,
            "ClientIp": settings.SERVER_IP,
            "Command": "namecheap.domains.check",
            "DomainList": domain,
        })
        # Parse XML response
        return "<Available>true</Available>" in r.text

async def purchase_domain(domain: str) -> dict:
    """Purchase a domain and immediately point to Cloudflare nameservers."""
    async with httpx.AsyncClient() as client:
        params = {
            "ApiUser": settings.NAMECHEAP_API_USER,
            "ApiKey": settings.NAMECHEAP_API_KEY,
            "UserName": settings.NAMECHEAP_API_USER,
            "ClientIp": settings.SERVER_IP,
            "Command": "namecheap.domains.create",
            "DomainName": domain,
            "Years": 1,
            # Nameservers → Cloudflare immediately
            "Nameservers": ",".join(CF_NAMESERVERS),
            # Contact info (use factory default)
            "RegistrantFirstName": settings.REGISTRANT_FIRST_NAME,
            "RegistrantLastName": settings.REGISTRANT_LAST_NAME,
            "RegistrantAddress1": settings.REGISTRANT_ADDRESS,
            "RegistrantCity": settings.REGISTRANT_CITY,
            "RegistrantStateProvince": settings.REGISTRANT_PROVINCE,
            "RegistrantPostalCode": settings.REGISTRANT_POSTAL_CODE,
            "RegistrantCountry": "CA",
            "RegistrantPhone": settings.REGISTRANT_PHONE,
            "RegistrantEmailAddress": settings.REGISTRANT_EMAIL,
            # Copy same for Tech, Admin, AuxBilling contacts
            # (Namecheap requires all 4 contact types)
        }
        # Add same contact for Tech, Admin, AuxBilling
        for prefix in ["Tech", "Admin", "AuxBilling"]:
            for field in ["FirstName", "LastName", "Address1", "City", "StateProvince", "PostalCode", "Country", "Phone", "EmailAddress"]:
                params[f"{prefix}{field}"] = params[f"Registrant{field}"]
        
        r = await client.get(BASE_URL, params=params)
        return {"success": "<ChargedAmount>" in r.text, "raw": r.text}
```

Build similar thin wrappers for: Cloudflare, Vercel, GitHub, Supabase, Stripe, Sendgrid, Instantly, Resend, Google Ads, Meta Ads, Google Search Console, Reddit, Slack, Retell AI, Twilio.

---

## KEY ARCHITECTURAL DECISIONS

1. **Single Postgres for everything.** Hatchet engine + factory data + pgvector embeddings (for RAG) in the same Postgres. Simpler ops. Hatchet uses its own schema/tables. pgvector replaces the need for a separate Qdrant/Pinecone.

2. **Agents communicate via DB + Hatchet triggers.** No message queue needed. Agent A writes to Postgres, then calls `hatchet.client.admin.run_workflow("agent-b", input={...})` to trigger Agent B. Agent B reads from Postgres.

3. **Prompt files are external.** System prompts live in `/prompts/*.txt`, not hardcoded. This lets you iterate on prompts without redeploying code.

4. **All agents log to `agent_logs`.** Every execution, every API call, every cost. This is how Self-Reflection analyzes everything.

5. **Budget Guardian as circuit breaker.** If API costs spike, it automatically downgrades Claude models (Opus→Sonnet, Sonnet→Haiku) for non-critical agents.

6. **Bilingual by default.** Every agent that produces customer-facing content MUST produce FR + EN. The i18n Agent validates.

7. **Canadian identity.** Pricing in CAD. Taxes by province. "Conçu au Canada" in footer. Not a flag, just professional subtle identity.

8. **Stripe single-account mode.** One Stripe account, all businesses. Customer metadata `{"business_id": X}` for separation. Separate Connected Accounts later when MRR justifies it.

9. **Voice calling is a first-class channel, not an afterthought.** For trades/contractors, phone > email. The Voice Agent is integrated into the Sales pipeline: after email 2 with no reply, if the lead has a phone and is DNCL-clear, the Voice Agent calls. Voice scripts are stored in Postgres (not hardcoded) so they can be A/B tested. Compliance (DNCL + calling hours + consent) is checked on EVERY call with zero exceptions.

10. **Retell AI over Vapi.** Retell is simpler ($0.07/min all-in vs Vapi's $0.18-0.33 effective), has a cleaner API, and doesn't require managing 4 separate vendor relationships. Twilio handles the telephony (Canadian numbers). If Retell doesn't work out, the integration layer is thin enough to swap for Vapi or Bland.ai.

11. **TWO email systems.** Sendgrid (or Resend for Next.js) for TRANSACTIONAL email (receipts, onboarding, dunning). Instantly.ai for COLD EMAIL (warmup, rotation, deliverability). NEVER send cold email through Sendgrid — it will destroy your domain reputation and eventually get your transactional emails blocked too.

12. **Postgres IS the CRM.** No HubSpot. The `leads` and `customers` tables with their status fields, notes, and source tracking are your CRM. If you need a UI, build a simple admin dashboard in Next.js. This eliminates an API integration, a monthly fee, and data sync issues.

13. **Self-hosted analytics (Plausible).** No GA4. Plausible is lighter, privacy-first (no cookie consent banner needed, which simplifies Loi 25 compliance), and you own the data. Added to Docker Compose.

14. **Namecheap for domain purchase → Cloudflare for DNS.** Cloudflare Registrar has no purchase API for non-Enterprise plans. Namecheap API supports .ca registration programmatically. Domains are purchased via Namecheap with nameservers immediately pointed to Cloudflare.

15. **Hetzner Object Storage for backups.** Same datacenter as the VPS = fast transfers, no egress fees. S3-compatible API so the backup script is identical to what you'd write for AWS S3.

16. **GEO (Generative Engine Optimization) is equal priority to SEO.** Every business site has `/llms.txt`, `/llms-full.txt`, Markdown versions of every page, schema.org on every page, and content written to be cited by LLMs — not just ranked by Google. The Content Engine writes articles that answer questions the way someone would ask Claude or ChatGPT, with specific quotable data points. This is the fastest-growing acquisition channel and most competitors ignore it completely.

17. **CEO Dashboard is the only human interface.** No Slack-scrolling, no logging into 12 different services. Everything — metrics, controls, decisions, agent performance, budget allocation — is in one FastAPI + HTMX dashboard at port 9000. If you can't control it from the dashboard, it shouldn't need human control.

---

## WHAT TO BUILD FIRST (priority order — see CRITICAL DESIGN CHANGES §1 above)

**The #1 rule: DO NOT build all 27 agents before you have a paying customer.**

### WAVE 1 — Ship & Sell (Days 1-10). Only these 7 agents + infra:
1. `docker-compose.yml` + `main.py` + `db.py` + `config.py` + `llm.py` + `base_agent.py` (with budget circuit breaker) — Get Hatchet + Postgres running
2. `outbound_sales.py` + `instantly_client.py` — THE most important agent. Revenue depends on this. Build first, test immediately. Use secondary sending domains. Follow 2026 cold email rules (§6 above).
3. `idea_factory.py` + `deep_scout.py` — Discovery pipeline (can run in parallel with building sales)
4. `brand_designer.py` (light mode only) + `domain_provisioner.py` — Just enough to get a name, domain, and infra
5. `builder.py` — Code the MVP. Pre-populated onboarding (§5). Reverse trial (§4). Flat-rate CAD pricing (§8). RLS enabled on every table (§12). Include llms.txt + schema.org from day 1.
6. `meta_orchestrator.py` — Coordinate the above
7. `analytics_agent.py` — Kill score, metrics, Slack reports. Track dev costs for SR&ED (§11).
8. `src/dashboard/` — Simple version first: overview + per-business controls + budget view

**MILESTONE: First cold emails sent. First paying customer.**

### WAVE 2 — Grow (Week 3-4, after first customer):
9. `content_engine.py` + GEO optimization — SEO + LLM citations. Compounds over time, start ASAP.
10. `social_agent.py` — Reddit + LinkedIn organic
11. `voice_agent.py` + `retell_client.py` + `twilio_client.py` + `dncl_client.py` — WARM CALLS ONLY (see §2). Only call leads who replied to email or signed up.
12. `billing_agent.py` — Dunning, Smart Retries, Card Updater, pre-expiry reminders (§7)
13. `support_agent.py` — RAG knowledge base
14. `fulfillment.py` — Per-business service delivery
15. `growth_hacker.py` — Marketplace listings, ecosystem integrations, template bait, trigger-based outreach

**MILESTONE: 10+ customers. Multiple acquisition channels working.**

### WAVE 3 — Optimize (Month 2+, after 10+ customers):
16. `self_reflection.py` — Meta-cognition (now there's enough data to analyze)
17. `referral_agent.py` + `email_nurture.py` + `upsell_agent.py` — Revenue expansion
18. `onboarding_agent.py` + `social_proof.py` — Improve activation & conversion
19. `competitor_watch.py` + `legal_guardrail.py` + `i18n_agent.py` — Monitoring & quality
20. `devops_agent.py` + `budget_guardian.py` — Infrastructure hardening
21. Dashboard v2: full controls, all metrics, agent performance

**MILESTONE: 3+ businesses live. Factory running autonomously.**

---

## TESTING

Each agent should have a test file. Use pytest + pytest-asyncio.

```python
# tests/test_idea_factory.py
import pytest
from src.agents.idea_factory import IdeaFactory

@pytest.mark.asyncio
async def test_score_ideas():
    """Test that ideas are scored correctly on 12 criteria."""
    agent = IdeaFactory()
    # Mock the scraping step, provide sample data
    result = await agent.score_ideas(mock_context_with_sample_ideas)
    assert all(0 <= idea["score"] <= 10 for idea in result["ideas"])
    assert all(len(idea["scoring_details"]) == 12 for idea in result["ideas"])
```

---

## ENV VARIABLES (.env)

**The .env file is now MINIMAL. All API keys are managed via the CEO Dashboard → Settings page (see §0 Setup Wizard above).**

The .env only contains what Docker Compose needs to boot:

```
# === THIS IS ALL YOU NEED IN .env ===

# Database (Docker Compose needs this)
POSTGRES_PASSWORD=your_strong_password_here

# Hatchet (Docker Compose needs this)
HATCHET_COOKIE_SECRET=your_random_secret_here

# Encryption (protects API keys stored in DB)
# Generate with: openssl rand -hex 32
ENCRYPTION_KEY=your_32_byte_hex_key_here

# CEO Dashboard auth
DASHBOARD_USER=ceo
DASHBOARD_PASSWORD=your_strong_password

# Factory config
DRY_RUN=true
FACTORY_TIMEZONE=America/Toronto
```

**That's it. 6 variables. Everything else goes through the dashboard.**

After `docker compose up`, open `http://[SERVER_IP]:9000`. The Setup Wizard walks you through connecting every service with test buttons. API keys are encrypted with AES-256-GCM and stored in the `secrets` table in Postgres.

For backwards compatibility, `settings.get("KEY_NAME")` checks the DB first, then falls back to `os.environ`. So if you prefer .env for some keys, that still works.

**Full list of secrets managed via Dashboard (for reference):**

| Category | Key | Required for |
|----------|-----|-------------|
| Core | ANTHROPIC_API_KEY | All AI agents |
| Core | SERPER_API_KEY | Lead Pipeline (Google Maps) |
| Core | SLACK_WEBHOOK_URL | Notifications |
| Lead Gen | APOLLO_API_KEY | Email enrichment |
| Lead Gen | HUNTER_API_KEY | Email enrichment (fallback) |
| Lead Gen | ZEROBOUNCE_API_KEY | Email verification |
| Lead Gen | SPARKTORO_API_KEY | Channel discovery |
| Lead Gen | SYFTEN_API_KEY | Community monitoring |
| Lead Gen | DATAFORSEO_API_KEY | Keyword research |
| Infrastructure | NAMECHEAP_API_KEY | Domain purchase |
| Infrastructure | NAMECHEAP_API_USER | Domain purchase |
| Infrastructure | CLOUDFLARE_API_TOKEN | DNS management |
| Infrastructure | VERCEL_TOKEN | Site deployment |
| Infrastructure | GITHUB_TOKEN | Repo management |
| Infrastructure | SUPABASE_ACCESS_TOKEN | DB provisioning |
| Infrastructure | STRIPE_SECRET_KEY | Billing |
| Infrastructure | STRIPE_WEBHOOK_SECRET | Billing events |
| Infrastructure | REGISTRANT_* (6 fields) | Domain WHOIS |
| Outreach | INSTANTLY_API_KEY | Cold email |
| Outreach | RESEND_API_KEY | Transactional email |
| Outreach | SENDGRID_API_KEY | Transactional email (agents) |
| Outreach | RETELL_API_KEY | Voice calls |
| Outreach | TWILIO_ACCOUNT_SID | Phone numbers |
| Outreach | TWILIO_AUTH_TOKEN | Phone numbers |
| Outreach | REDDIT_* (4 fields) | Social agent |
| Optional | GOOGLE_ADS_* (4 fields) | Validation ads |
| Optional | META_ADS_* (2 fields) | Validation ads |
| Optional | HETZNER_S3_* (4 fields) | Backups |
| Optional | PLAUSIBLE_* (2 fields) | Analytics |

---

## IMPORTANT: GAPS FOUND IN SIMULATION (must be addressed)

These gaps were found by simulating the full lifecycle. The code must handle them:

1. **GAP-01:** Validator needs Brand Agent BEFORE creating landing page → Brand Agent has `light` mode
2. **GAP-02:** Meta/Google Ads accounts must exist before Validator runs → setup checklist item
3. **GAP-05:** Stripe KYC blocks auto-provisioning → single Stripe account mode with metadata
4. **GAP-07:** Template Next.js repo must exist → create once, clone for each business
5. **GAP-08:** Business-specific pricing data (e.g., roofing material costs) → Scout Report includes data section + first customers customize during onboarding
6. **GAP-09:** Logo → text-based logo using Brand Kit heading font (no image generation needed for MVP)
7. **GAP-10:** Legal templates → use Termly/iubenda API or static templates with variables
8. **GAP-13:** Email warm-up required before cold outreach → Domain Provisioner sets `email_warmup_start` date, Sales Agent checks `warmup_complete` (14 days later) before sending volume
9. **GAP-15:** Knowledge base empty at launch → Builder generates initial docs as last step
10. **GAP-17:** Blog section must exist in MVP template → include MDX blog in template repo
11. **GAP-19:** Tax registration required at $30K/year → Analytics Agent alerts when MRR approaches $2,500/month
12. **GAP-20:** DNCL subscription must be active BEFORE any outbound voice call → Setup checklist item: register at https://lnnte-dncl.gc.ca/, subscribe to area codes (514, 438, 418, 416, 647, 604, etc.), download initial DNCL file, load into dncl_cache table. Cost: ~$55-2,740 CAD/year. Monthly refresh cron job required.
13. **GAP-21:** Canadian phone numbers needed for caller ID → Domain Provisioner must buy Twilio phone numbers per business (local area code for credibility: 514 for QC, 416 for ON, etc.). Cost: ~$1.50/month per number + usage.
14. **GAP-22:** Voice agent scripts need human review before first call campaign → Add a step where the Sales Agent logs the first script to Slack for human approval before launching volume. After approval, fully autonomous.
15. **GAP-23:** Retell AI webhook endpoint needed → The factory-worker must expose an HTTP endpoint for Retell call-completion webhooks. Add a webhook handler route in main.py or use Hatchet's webhook trigger feature.
16. **GAP-24:** Voice call recordings storage → Retell provides recording URLs but they expire. If you need long-term storage (for compliance/training), download recordings to S3/Backblaze within 24h of call completion. DevOps Agent handles this.

---

## FINAL NOTES FOR CURSOR

- Use `httpx` for all HTTP calls (async)
- Use `sqlalchemy` for DB (async with `asyncpg`)
- Use `pydantic` for all data models and validation
- Use `structlog` for structured logging
- Every agent catches exceptions and logs to `agent_logs` with status='error'
- Every agent tracks execution time and API cost
- All customer-facing text: FR + EN, no exceptions
- All prices: CAD with proper tax handling by province
- Run `black` + `ruff` for formatting/linting
- Type hints everywhere
- **VOICE COMPLIANCE IS NON-NEGOTIABLE:** The voice_agent MUST check DNCL + internal DNC + calling hours BEFORE every single outbound call. If any check fails, the call MUST NOT be made. There is no "override" or "skip for testing." This is Canadian law.
- **Voice call flow:** Sales Agent decides who to call → Voice Agent checks compliance → if clear, makes call via Retell AI → processes result → updates lead/customer status. The Sales Agent NEVER calls directly — it always goes through the Voice Agent's compliance pipeline.
- **Voice cost tracking:** Retell AI charges ~$0.07/min, Twilio charges ~$0.01/min for PSTN. A 2-minute cold call costs ~$0.16. At 30 calls/day = ~$4.80/day. Budget Guardian must track this.

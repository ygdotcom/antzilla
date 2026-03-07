-- Factory initial schema
-- Run against: pgvector/pgvector:pg16

-- ═══ EXTENSIONS ═══
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══ CORE ENTITIES ═══

CREATE TABLE ideas (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    niche TEXT,
    us_equivalent TEXT,
    us_equivalent_url TEXT,
    ca_gap_analysis TEXT,
    score NUMERIC(3,1),
    scoring_details JSONB,
    status TEXT DEFAULT 'new' CHECK (status IN ('new','scouting','scouted','validating','validated','approved','building','live','killed')),
    scout_report TEXT,
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
    brand_kit JSONB,
    pricing JSONB,
    icp JSONB,
    config JSONB,
    mrr NUMERIC(10,2) DEFAULT 0,
    customers_count INT DEFAULT 0,
    kill_score NUMERIC(5,2),
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
    province TEXT,
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
    source TEXT CHECK (source IN (
        'google_maps','rbq_registry','req_registry','federal_corp',
        'association_directory','industry_directory','cold_email',
        'reddit','seo','referral','ads','linkedin','facebook_group',
        'product_hunt','organic','website_visitor','signal','other'
    )),
    source_url TEXT,
    consent_type TEXT CHECK (consent_type IN (
        'conspicuous_publication','business_relationship','express','inquiry','none'
    )),
    status TEXT DEFAULT 'new' CHECK (status IN (
        'new','enriching','enriched','contacted','replied',
        'booked','trial','converted','lost','unsubscribed'
    )),
    language TEXT DEFAULT 'fr',
    province TEXT,
    score INT DEFAULT 0,
    enrichment_data JSONB,
    enrichment_sources TEXT[],
    signal_type TEXT,
    signal_date TIMESTAMPTZ,
    signal_data JSONB,
    notes TEXT,
    sequence_step INT DEFAULT 0,
    sequence_channel TEXT DEFAULT 'email',
    last_contacted_at TIMESTAMPTZ,
    replied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ GTM PLAYBOOKS ═══

CREATE TABLE gtm_playbooks (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) UNIQUE,
    config JSONB NOT NULL,
    version INT DEFAULT 1,
    last_updated_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ BUYING SIGNALS ═══

CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    lead_id INT REFERENCES leads(id),
    signal_type TEXT NOT NULL,
    source TEXT,
    data JSONB,
    weight INT,
    actioned BOOLEAN DEFAULT FALSE,
    actioned_at TIMESTAMPTZ,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ OUTREACH EXPERIMENTS ═══

CREATE TABLE outreach_experiments (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    experiment_name TEXT,
    variant_a TEXT,
    variant_b TEXT,
    sends_a INT DEFAULT 0,
    sends_b INT DEFAULT 0,
    replies_a INT DEFAULT 0,
    replies_b INT DEFAULT 0,
    positive_replies_a INT DEFAULT 0,
    positive_replies_b INT DEFAULT 0,
    winner TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ CONTENT & MARKETING ═══

CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    type TEXT CHECK (type IN ('blog_fr','blog_en','landing_page','social_post','email_template','case_study','faq')),
    title TEXT,
    slug TEXT,
    body TEXT,
    keywords TEXT[],
    meta_description TEXT,
    url TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','published','indexed','ranked','killed')),
    metrics JSONB,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE social_posts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    platform TEXT CHECK (platform IN ('reddit','linkedin','twitter','facebook_group')),
    community TEXT,
    post_type TEXT CHECK (post_type IN ('post','comment','reply')),
    content TEXT,
    url TEXT,
    utm_link TEXT,
    engagement JSONB,
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
    job_type TEXT,
    input_data JSONB,
    output_data JSONB,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','escalated')),
    deliverables JSONB,
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
    messages JSONB,
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
    published_where TEXT,
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
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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
    dncl_checked BOOLEAN DEFAULT FALSE,
    dncl_clear BOOLEAN,
    retell_call_id TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','ringing','in_progress','completed','failed','no_answer','voicemail','declined')),
    duration_seconds INT,
    transcript TEXT,
    summary TEXT,
    outcome TEXT CHECK (outcome IN ('interested','not_interested','callback_requested','meeting_booked','wrong_number','voicemail_left','do_not_call','escalate')),
    meeting_booked_url TEXT,
    cost_usd NUMERIC(8,4),
    recording_url TEXT,
    script_variant TEXT,
    sentiment_score NUMERIC(3,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE dncl_cache (
    id SERIAL PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    on_dncl BOOLEAN NOT NULL,
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')
);

CREATE TABLE voice_scripts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    call_type TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('fr','en')),
    name TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    greeting TEXT NOT NULL,
    objection_handlers JSONB,
    success_criteria TEXT,
    max_duration_seconds INT DEFAULT 120,
    active BOOLEAN DEFAULT TRUE,
    metrics JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ INTELLIGENCE ═══

CREATE TABLE agent_logs (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    business_id INT REFERENCES businesses(id),
    workflow_run_id TEXT,
    action TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    result JSONB,
    status TEXT DEFAULT 'success' CHECK (status IN ('success','error','retry','skipped')),
    cost_usd NUMERIC(8,4),
    duration_seconds NUMERIC(8,2),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE improvements (
    id SERIAL PRIMARY KEY,
    proposed_by TEXT DEFAULT 'self_reflection',
    target_agent TEXT,
    business_id INT REFERENCES businesses(id),
    category TEXT CHECK (category IN (
        'recurring_error','missed_opportunity','inefficiency',
        'blind_spot','cross_learning','drift','quality','new_idea'
    )),
    description TEXT NOT NULL,
    proposed_action TEXT NOT NULL,
    evidence TEXT,
    impact_score NUMERIC(3,1),
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical','high','medium','low')),
    status TEXT DEFAULT 'proposed' CHECK (status IN ('proposed','approved','implementing','implemented','rejected')),
    outcome TEXT,
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
    metrics JSONB,
    UNIQUE(business_id, date)
);

CREATE TABLE budget_tracking (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    agent_name TEXT,
    business_id INT REFERENCES businesses(id),
    api_provider TEXT,
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

-- ═══ SECRETS (encrypted API keys, managed via CEO Dashboard) ═══

CREATE TABLE secrets (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value_encrypted TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('core','lead_gen','infrastructure','outreach','optional')),
    display_name TEXT,
    is_configured BOOLEAN DEFAULT FALSE,
    last_tested_at TIMESTAMPTZ,
    last_test_status TEXT DEFAULT 'untested' CHECK (last_test_status IN ('ok','failed','untested')),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ BRAND MENTIONS (reputation monitoring) ═══

CREATE TABLE brand_mentions (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    platform TEXT NOT NULL,
    community TEXT,
    content TEXT NOT NULL,
    sentiment FLOAT,
    is_negative BOOLEAN DEFAULT FALSE,
    url TEXT,
    actioned BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ FEATURE REQUESTS (product iteration loop) ═══

CREATE TABLE feature_requests (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id),
    title TEXT NOT NULL,
    description TEXT,
    requested_by_count INT DEFAULT 1,
    customer_ids INT[],
    priority_score FLOAT DEFAULT 0,
    status TEXT DEFAULT 'proposed' CHECK (status IN ('proposed','approved','building','shipped','rejected')),
    github_pr_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ FACTORY KNOWLEDGE (cross-business learning — the factory's long-term memory) ═══

CREATE TABLE factory_knowledge (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN (
        'email_template_winner',
        'channel_effectiveness',
        'idea_scoring_calibration',
        'objection_response',
        'icp_insight',
        'pricing_insight',
        'content_format_winner',
        'onboarding_pattern',
        'churn_reason',
        'referral_tactic'
    )),
    vertical TEXT,
    insight TEXT NOT NULL,
    data JSONB NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    times_applied INT DEFAULT 0,
    times_successful INT DEFAULT 0,
    source_business_id INT REFERENCES businesses(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
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
CREATE INDEX idx_kb_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_kb_business ON knowledge_base(business_id, source);
CREATE INDEX idx_signals_business ON signals(business_id, signal_type);
CREATE INDEX idx_signals_lead ON signals(lead_id);
CREATE INDEX idx_gtm_playbooks_business ON gtm_playbooks(business_id);
CREATE INDEX idx_outreach_experiments_business ON outreach_experiments(business_id);
CREATE INDEX idx_brand_mentions_business ON brand_mentions(business_id, platform, detected_at DESC);
CREATE INDEX idx_feature_requests_business ON feature_requests(business_id, status, priority_score DESC);
CREATE INDEX idx_factory_knowledge_category ON factory_knowledge(category, vertical);
CREATE INDEX idx_factory_knowledge_confidence ON factory_knowledge(confidence DESC);

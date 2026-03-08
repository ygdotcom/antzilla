-- Template Next.js SaaS app — initial schema
-- SPEC §12: Every table MUST have RLS enabled and at least one policy.

-- ═══ PROFILES (extends auth.users) ═══
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    company TEXT,
    phone TEXT,
    language TEXT DEFAULT 'fr' CHECK (language IN ('fr', 'en')),
    province TEXT,
    avatar_url TEXT,
    stripe_customer_id TEXT,
    onboarding_step INT DEFAULT 0,
    onboarding_complete BOOLEAN DEFAULT FALSE,
    referral_code TEXT UNIQUE,
    referred_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile"
    ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own profile"
    ON profiles FOR INSERT WITH CHECK (auth.uid() = id);

CREATE INDEX IF NOT EXISTS idx_profiles_referral_code ON profiles(referral_code);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe ON profiles(stripe_customer_id);

-- ═══ PROJECTS (user work items — renamed from 'title' to 'name' for consistency) ═══
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
    data JSONB DEFAULT '{}',
    is_sample BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own projects"
    ON projects FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);

-- ═══ SUBSCRIPTIONS ═══
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT UNIQUE,
    plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'business')),
    status TEXT DEFAULT 'active' CHECK (status IN ('trialing', 'active', 'past_due', 'canceled')),
    trial_end TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own subscription"
    ON subscriptions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own subscription"
    ON subscriptions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own subscription"
    ON subscriptions FOR UPDATE USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe ON subscriptions(stripe_customer_id);

-- ═══ REFERRALS ═══
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    referee_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    referral_code TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'signed_up', 'converted', 'rewarded')),
    reward_applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can see own referrals"
    ON referrals FOR SELECT
    USING (auth.uid() = referrer_id OR auth.uid() = referee_id);
CREATE POLICY "Users can insert referrals"
    ON referrals FOR INSERT WITH CHECK (auth.uid() = referrer_id);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code);

-- ═══ AGGREGATE_STATS (data flywheel) ═══
CREATE TABLE IF NOT EXISTS aggregate_stats (
    id SERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC NOT NULL,
    period TEXT,
    region TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE aggregate_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON aggregate_stats FOR SELECT USING (true);

-- ═══ FUNCTIONS ═══
CREATE OR REPLACE FUNCTION generate_referral_code()
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    result TEXT := '';
    i INT;
BEGIN
    FOR i IN 1..8 LOOP
        result := result || substr(chars, floor(random() * length(chars) + 1)::int, 1);
    END LOOP;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    new_code TEXT;
    code_exists BOOLEAN;
BEGIN
    LOOP
        new_code := generate_referral_code();
        SELECT EXISTS(SELECT 1 FROM profiles WHERE referral_code = new_code) INTO code_exists;
        EXIT WHEN NOT code_exists;
    END LOOP;

    INSERT INTO public.profiles (id, full_name, referral_code)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
        new_code
    );

    -- Create sample project for onboarding
    INSERT INTO public.projects (user_id, name, description, is_sample, status)
    VALUES (
        NEW.id,
        'Sample Project',
        'This is a sample project to help you get started. Feel free to edit or delete it.',
        TRUE,
        'active'
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

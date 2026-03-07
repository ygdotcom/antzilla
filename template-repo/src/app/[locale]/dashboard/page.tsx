import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { createClient } from '@/lib/supabase/server';
import { OnboardingChecklist } from '@/components/onboarding-checklist';
import { ReverseTrialBanner } from '@/components/reverse-trial-banner';
import { LanguageToggle } from '@/components/language-toggle';
import { DashboardClient } from './dashboard-client';

export default async function DashboardPage() {
  const supabase = await createClient();
  const t = await getTranslations('dashboard');

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect('/auth/login');
  }

  const { data: profile } = await supabase
    .from('profiles')
    .select('*')
    .eq('id', user.id)
    .single();

  const { data: subscription } = await supabase
    .from('subscriptions')
    .select('*')
    .eq('user_id', user.id)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();

  const { data: projects } = await supabase
    .from('projects')
    .select('*')
    .eq('user_id', user.id)
    .order('created_at', { ascending: false });

  const hasSampleProject =
    projects?.some((p) => p.is_sample) ?? false;

  if (!hasSampleProject && projects?.length === 0) {
    await supabase.from('projects').insert({
      user_id: user.id,
      name: t('sampleProject'),
      description: t('sampleDescription'),
      is_sample: true,
    });
  }

  const { data: allProjects } = await supabase
    .from('projects')
    .select('*')
    .eq('user_id', user.id)
    .order('created_at', { ascending: false });

  const onboardingComplete = profile?.onboarding_complete ?? false;

  const trialEnd = subscription?.trial_end
    ? new Date(subscription.trial_end)
    : null;
  const now = new Date();
  const trialDaysLeft =
    trialEnd && trialEnd > now
      ? Math.ceil((trialEnd.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
      : null;
  const trialEnded =
    trialEnd !== null &&
    trialEnd <= now &&
    subscription?.status !== 'active';

  const onboardingSteps = [
    {
      id: 'explore',
      label: t('onboarding.step1'),
      completed: (allProjects ?? []).some(
        (p) => p.is_sample && p.updated_at !== p.created_at
      ),
    },
    {
      id: 'create',
      label: t('onboarding.step2'),
      completed: (allProjects ?? []).some((p) => !p.is_sample),
    },
    {
      id: 'invite',
      label: t('onboarding.step3'),
      completed: false,
    },
    {
      id: 'connect',
      label: t('onboarding.step4'),
      completed: false,
    },
  ];

  const completedSteps = onboardingSteps.filter((s) => s.completed).length;
  const progress = completedSteps / onboardingSteps.length;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <h1 className="text-xl font-bold">{t('title')}</h1>
          <div className="flex items-center gap-4">
            <LanguageToggle />
            <form action="/auth/logout" method="post">
              <button
                type="submit"
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Log out
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <h2 className="mb-8 text-2xl font-semibold text-gray-900">
          {t('welcomeBack', { name: profile?.full_name || '' })}
        </h2>

        <div className="space-y-6">
          <DashboardClient
            trialDaysLeft={trialDaysLeft}
            trialEnded={trialEnded}
            onboardingComplete={onboardingComplete}
            onboardingSteps={onboardingSteps}
            onboardingProgress={progress}
            projects={allProjects ?? []}
            userId={user.id}
          />
        </div>
      </main>
    </div>
  );
}

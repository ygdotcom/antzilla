'use client';

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { OnboardingChecklist, type OnboardingStep } from '@/components/onboarding-checklist';
import { ReverseTrialBanner } from '@/components/reverse-trial-banner';
import { createClient } from '@/lib/supabase/client';

interface Project {
  id: string;
  name: string;
  description: string | null;
  is_sample: boolean;
  created_at: string;
}

interface DashboardClientProps {
  trialDaysLeft: number | null;
  trialEnded: boolean;
  onboardingComplete: boolean;
  onboardingSteps: OnboardingStep[];
  onboardingProgress: number;
  projects: Project[];
  userId: string;
}

export function DashboardClient({
  trialDaysLeft,
  trialEnded,
  onboardingComplete,
  onboardingSteps,
  onboardingProgress,
  projects,
  userId,
}: DashboardClientProps) {
  const router = useRouter();
  const t = useTranslations('dashboard');

  async function handleDismissOnboarding() {
    const supabase = createClient();
    await supabase
      .from('profiles')
      .update({ onboarding_complete: true })
      .eq('id', userId);
    router.refresh();
  }

  function handleUpgrade() {
    router.push('/pricing');
  }

  return (
    <>
      {(trialDaysLeft !== null || trialEnded) && (
        <ReverseTrialBanner
          trialDaysLeft={trialDaysLeft}
          trialEnded={trialEnded}
          onUpgrade={handleUpgrade}
        />
      )}

      {!onboardingComplete && (
        <OnboardingChecklist
          steps={onboardingSteps}
          progress={onboardingProgress}
          onDismiss={handleDismissOnboarding}
        />
      )}

      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Projects</h3>
        <a
          href="/dashboard/new"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t('createNew')}
        </a>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((project) => (
          <div
            key={project.id}
            className="rounded-xl border border-gray-200 bg-white p-5 transition hover:shadow-md"
          >
            <div className="flex items-start justify-between">
              <h4 className="font-semibold text-gray-900">{project.name}</h4>
              {project.is_sample && (
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600">
                  Sample
                </span>
              )}
            </div>
            {project.description && (
              <p className="mt-2 text-sm text-gray-500">
                {project.description}
              </p>
            )}
            <p className="mt-3 text-xs text-gray-400">
              {new Date(project.created_at).toLocaleDateString()}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

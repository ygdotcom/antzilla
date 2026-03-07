'use client';

import { useState } from 'react';
import * as Progress from '@radix-ui/react-progress';
import { useTranslations } from 'next-intl';

export interface OnboardingStep {
  id: string;
  label: string;
  completed: boolean;
}

interface OnboardingChecklistProps {
  steps: OnboardingStep[];
  progress: number;
  onDismiss: () => void;
}

export function OnboardingChecklist({
  steps,
  progress,
  onDismiss,
}: OnboardingChecklistProps) {
  const t = useTranslations('dashboard.onboarding');
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const completedCount = steps.filter((s) => s.completed).length;
  const percentage = Math.round(progress * 100);

  function handleDismiss() {
    setDismissed(true);
    onDismiss();
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">{t('title')}</h3>
        <span className="text-sm text-gray-500">
          {t('progress', { completed: completedCount, total: steps.length })}
        </span>
      </div>

      <Progress.Root
        className="relative mb-6 h-2 w-full overflow-hidden rounded-full bg-gray-100"
        value={percentage}
      >
        <Progress.Indicator
          className="h-full rounded-full bg-blue-600 transition-all duration-500 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </Progress.Root>

      <ul className="mb-6 space-y-3">
        {steps.map((step) => (
          <li key={step.id} className="flex items-center gap-3">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sm ${
                step.completed
                  ? 'bg-green-100 text-green-600'
                  : 'border border-gray-300 text-gray-400'
              }`}
            >
              {step.completed ? '✓' : ''}
            </span>
            <span
              className={`text-sm ${
                step.completed
                  ? 'text-gray-500 line-through'
                  : 'text-gray-900'
              }`}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ul>

      <button
        onClick={handleDismiss}
        className="text-sm text-gray-500 underline underline-offset-2 hover:text-gray-700"
      >
        {t.has('dismiss') ? t('dismiss') : 'Dismiss'}
      </button>
    </div>
  );
}

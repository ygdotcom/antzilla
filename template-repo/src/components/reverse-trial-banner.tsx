'use client';

import { useTranslations } from 'next-intl';
import { PLAN_FEATURES } from '@/lib/stripe';

interface ReverseTrialBannerProps {
  trialDaysLeft: number | null;
  trialEnded: boolean;
  onUpgrade: () => void;
}

const PREMIUM_FEATURES_LOST = PLAN_FEATURES.pro.filter(
  (f) => !PLAN_FEATURES.free.includes(f)
);

export function ReverseTrialBanner({
  trialDaysLeft,
  trialEnded,
  onUpgrade,
}: ReverseTrialBannerProps) {
  const t = useTranslations('trial');

  if (!trialEnded && trialDaysLeft === null) return null;

  if (trialEnded) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <h3 className="text-lg font-semibold text-red-900">
          {t('trialEnded')}
        </h3>
        <p className="mt-1 text-sm text-red-700">{t('losingAccess')}</p>

        <ul className="mt-3 space-y-2">
          {PREMIUM_FEATURES_LOST.map((feature) => (
            <li
              key={feature}
              className="flex items-center gap-2 text-sm text-red-700"
            >
              <span className="text-red-400">✕</span>
              {feature}
            </li>
          ))}
        </ul>

        <button
          onClick={onUpgrade}
          className="mt-5 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-red-700"
        >
          {t('keepFeatures')}
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-6 py-4">
      <div>
        <p className="font-medium text-amber-900">
          {t('daysLeft', { days: trialDaysLeft })}
        </p>
        <p className="mt-0.5 text-sm text-amber-700">
          {t('losingAccess')}
        </p>
      </div>
      <button
        onClick={onUpgrade}
        className="shrink-0 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-amber-700"
      >
        {t('upgradeNow')}
      </button>
    </div>
  );
}

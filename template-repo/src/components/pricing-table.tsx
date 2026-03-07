'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { PLAN_FEATURES, type Plan } from '@/lib/stripe';

interface Tier {
  plan: Plan;
  monthlyPrice: number;
  annualPrice: number;
  features: string[];
  highlighted?: boolean;
}

const TIERS: Tier[] = [
  {
    plan: 'free',
    monthlyPrice: 0,
    annualPrice: 0,
    features: PLAN_FEATURES.free,
  },
  {
    plan: 'pro',
    monthlyPrice: 49,
    annualPrice: 41,
    features: PLAN_FEATURES.pro,
    highlighted: true,
  },
  {
    plan: 'business',
    monthlyPrice: 99,
    annualPrice: 82,
    features: PLAN_FEATURES.business,
  },
];

function formatPrice(price: number): string {
  return `$${price}`;
}

function annualSavings(monthly: number, annual: number): number {
  return (monthly - annual) * 12;
}

interface PricingTableProps {
  currentPlan?: Plan;
  onSelectPlan?: (plan: Plan, billing: 'monthly' | 'annual') => void;
}

export function PricingTable({ currentPlan, onSelectPlan }: PricingTableProps) {
  const t = useTranslations('pricing');
  const [billing, setBilling] = useState<'monthly' | 'annual'>('monthly');

  return (
    <div>
      <div className="mb-10 flex items-center justify-center gap-3">
        <button
          onClick={() => setBilling('monthly')}
          className={`rounded-full px-4 py-2 text-sm font-medium transition ${
            billing === 'monthly'
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          {t('monthly')}
        </button>
        <button
          onClick={() => setBilling('annual')}
          className={`rounded-full px-4 py-2 text-sm font-medium transition ${
            billing === 'annual'
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          {t('annual')}
          <span className="ml-1.5 inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
            {t('annualSave')}
          </span>
        </button>
      </div>

      <div className="mx-auto grid max-w-5xl gap-6 md:grid-cols-3">
        {TIERS.map((tier) => {
          const price =
            billing === 'monthly' ? tier.monthlyPrice : tier.annualPrice;
          const isCurrent = currentPlan === tier.plan;
          const savings = annualSavings(tier.monthlyPrice, tier.annualPrice);

          return (
            <div
              key={tier.plan}
              className={`relative rounded-2xl border p-8 ${
                tier.highlighted
                  ? 'border-blue-600 shadow-lg ring-1 ring-blue-600'
                  : 'border-gray-200'
              }`}
            >
              {tier.highlighted && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white">
                  {t('recommended')}
                </span>
              )}

              <h3 className="text-lg font-semibold text-gray-900">
                {t(`${tier.plan}Tier`)}
              </h3>

              <div className="mt-4 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-gray-900">
                  {formatPrice(price)}
                </span>
                {price > 0 && (
                  <span className="text-sm text-gray-500">{t('perMonth')}</span>
                )}
              </div>

              {billing === 'annual' && savings > 0 && (
                <p className="mt-1 text-sm text-green-600">
                  {t('annualSave')} — ${savings}/yr
                </p>
              )}

              <ul className="mt-6 space-y-3">
                {tier.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-start gap-2 text-sm text-gray-700"
                  >
                    <span className="mt-0.5 text-green-500">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>

              <button
                disabled={isCurrent}
                onClick={() => onSelectPlan?.(tier.plan, billing)}
                className={`mt-8 w-full rounded-lg px-4 py-2.5 text-sm font-medium transition ${
                  isCurrent
                    ? 'cursor-default bg-gray-100 text-gray-400'
                    : tier.highlighted
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-gray-900 text-white hover:bg-gray-800'
                }`}
              >
                {isCurrent
                  ? t('currentPlan')
                  : price === 0
                    ? t('freeTier')
                    : t('startTrial')}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

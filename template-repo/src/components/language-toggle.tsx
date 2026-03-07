'use client';

import { useLocale } from 'next-intl';
import { useRouter, usePathname } from 'next/navigation';
import type { Locale } from '@/i18n/routing';

const LOCALE_LABELS: Record<Locale, string> = {
  fr: 'FR',
  en: 'EN',
};

export function LanguageToggle() {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(target: Locale) {
    if (target === locale) return;

    const segments = pathname.split('/');
    segments[1] = target;
    router.push(segments.join('/'));
  }

  const otherLocale: Locale = locale === 'fr' ? 'en' : 'fr';

  return (
    <button
      onClick={() => switchLocale(otherLocale)}
      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
      aria-label={`Switch to ${LOCALE_LABELS[otherLocale]}`}
    >
      {LOCALE_LABELS[otherLocale]}
    </button>
  );
}
